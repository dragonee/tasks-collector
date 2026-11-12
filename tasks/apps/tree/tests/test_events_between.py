"""The days of a span in one request (api/events/), as api/events/daily/
gives them one at a time."""

import datetime

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from ..models import (
    JournalAdded,
    Observation,
    ObservationType,
    ObservationUpdated,
    Thread,
)
from .factories import make_reflection, make_thread

MONDAY = datetime.date(2026, 11, 2)
SUNDAY = datetime.date(2026, 11, 8)


def at(day, hour=12):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))


class EventsBetweenTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.other = User.objects.create_user(username="o", password="x")
        cls.daily = Thread.objects.daily(cls.user)
        cls.weekly = make_thread(cls.user, Thread.WEEKLY)

        for day, comment in (
            (MONDAY, "Monday's entry"),
            (MONDAY, "Monday, later"),
            (SUNDAY, "Sunday's entry"),
            (SUNDAY + datetime.timedelta(days=1), "The Monday after"),
        ):
            JournalAdded.objects.create(
                thread=cls.daily, comment=comment, published=at(day)
            )
        make_reflection(
            cls.daily, MONDAY + datetime.timedelta(days=2), good="Wednesday"
        )
        JournalAdded.objects.create(
            thread=cls.weekly, comment="The week", published=at(SUNDAY, 23)
        )
        JournalAdded.objects.create(
            thread=Thread.objects.daily(cls.other),
            comment="Someone else's",
            published=at(MONDAY),
        )

    def setUp(self):
        self.client.force_authenticate(self.user)

    def _get(self, **params):
        return self.client.get(reverse("events-between"), params)

    def test_the_days_with_something_on_them(self):
        response = self._get(**{"from": MONDAY, "to": SUNDAY})

        self.assertEqual(response.status_code, 200)
        days = response.json()["days"]
        self.assertEqual(
            [day["date"] for day in days], ["2026-11-02", "2026-11-04", "2026-11-08"]
        )
        self.assertEqual(
            [event["comment"] for event in days[0]["events"]],
            ["Monday's entry", "Monday, later"],
        )
        self.assertEqual(days[1]["events"], [])
        self.assertEqual(days[1]["reflection"]["good"], "Wednesday")

    def test_the_same_as_a_day_at_a_time(self):
        day = self.client.get(reverse("daily-events"), {"date": MONDAY}).json()

        span = self._get(**{"from": MONDAY, "to": MONDAY}).json()["days"]

        self.assertEqual(span, [day])

    def test_another_thread(self):
        days = self._get(**{"from": MONDAY, "to": SUNDAY, "thread": "Weekly"}).json()[
            "days"
        ]

        self.assertEqual(
            [event["comment"] for day in days for event in day["events"]], ["The week"]
        )

    def test_what_it_refuses(self):
        for params in (
            {"from": MONDAY},
            {"from": "Monday", "to": SUNDAY},
            {"from": SUNDAY, "to": MONDAY},
            {"from": MONDAY, "to": MONDAY + datetime.timedelta(days=366)},
            {"from": MONDAY, "to": SUNDAY, "thread": "No such thread"},
        ):
            with self.subTest(params):
                self.assertEqual(self._get(**params).status_code, 400)

    def test_a_day_that_is_not_a_date(self):
        response = self.client.get(reverse("daily-events"), {"date": "x"})

        self.assertEqual(response.status_code, 400)

    def test_a_year_at_once(self):
        response = self._get(**{"from": MONDAY, "to": MONDAY + datetime.timedelta(365)})

        self.assertEqual(response.status_code, 200)

    def test_an_update_whose_observation_has_no_situation_on_record(self):
        # Made without the events that record its situation, as an old
        # observation whose ObservationMade was lost.
        observation = Observation.objects.create(
            user=self.user,
            thread=self.daily,
            type=ObservationType.objects.create(name="Error", slug="error"),
            pub_date=MONDAY,
        )
        ObservationUpdated.objects.create(
            observation=observation, comment="still", published=at(MONDAY, 9)
        )

        span = self._get(**{"from": MONDAY, "to": MONDAY})
        day = self.client.get(reverse("daily-events"), {"date": MONDAY})

        self.assertEqual((span.status_code, day.status_code), (200, 200))
        for events in (span.json()["days"][0]["events"], day.json()["events"]):
            self.assertEqual(
                [
                    (event["comment"], event["situation_at_creation"])
                    for event in events
                    if event["resourcetype"] == "ObservationUpdated"
                ],
                [("still", "")],
            )
