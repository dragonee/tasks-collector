"""A send retried with the same idempotency_key (tc queues one that failed
and sends it again) makes nothing twice: journal entries, observations,
their updates and tracked habits."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase

from ..models import (
    HabitTracked,
    JournalAdded,
    Observation,
    ObservationMade,
    ObservationType,
    ObservationUpdated,
    ReflectionLine,
)
from .factories import make_habit

KEY = "0b5c1d0e7a534d0b9d532f6d3c1f5a11"


class IdempotentSendTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.other = User.objects.create_user(username="o", password="x")
        cls.type = ObservationType.objects.create(name="Error", slug="error")
        make_habit(cls.user, "Workout", keywords=["workout"])
        make_habit(cls.user, "Food", keywords=["food"])

    def setUp(self):
        self.client.force_authenticate(self.user)

    def _post(self, url, payload):
        return self.client.post(url, payload, format="json")

    def _twice(self, url, payload):
        return self._post(url, payload), self._post(url, payload)

    def test_a_journal_entry(self):
        entry = {
            "comment": "- [x] Went running #workout",
            "thread": "Daily",
            "published": "2026-11-11T20:00:00+00:00",
            "tags": [],
            "idempotency_key": KEY,
        }

        first, again = self._twice("/journal/", entry)

        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertEqual(JournalAdded.objects.count(), 1)
        self.assertEqual(ReflectionLine.objects.count(), 1)
        self.assertEqual(HabitTracked.objects.count(), 1)

    def test_entries_without_a_key_are_all_added(self):
        entry = {"comment": "hello", "thread": "Daily", "tags": []}

        for key in (None, ""):
            with self.subTest(key=key):
                self._twice("/journal/", entry | {"idempotency_key": key})

        self.assertEqual(JournalAdded.objects.count(), 4)

    def test_keys_are_each_users_own(self):
        entry = {
            "comment": "hello",
            "thread": "Daily",
            "tags": [],
            "idempotency_key": KEY,
        }
        self._post("/journal/", entry)
        self.client.force_authenticate(self.other)

        response = self._post("/journal/", entry)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(JournalAdded.objects.count(), 2)

    def test_an_observation(self):
        observation = {
            "pub_date": "2026-11-11",
            "thread": "Daily",
            "type": "error",
            "situation": "it broke",
            "idempotency_key": KEY,
        }

        first, again = self._twice("/observation-api/", observation)

        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertEqual(Observation.objects.count(), 1)
        self.assertEqual(ObservationMade.objects.get().idempotency_key, KEY)

    def test_an_update(self):
        observation = self._post(
            "/observation-api/",
            {
                "pub_date": "2026-11-11",
                "thread": "Daily",
                "type": "error",
                "situation": "x",
            },
        ).json()

        first, again = self._twice(
            "/updates/",
            {
                "observation": observation["id"],
                "comment": "still",
                "idempotency_key": KEY,
            },
        )

        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(ObservationUpdated.objects.count(), 1)

    def test_a_line_of_habits(self):
        line = {
            "text": "#workout 100 push-ups #food salad",
            "published": "2026-11-11T20:00:00+00:00",
            "idempotency_key": KEY,
        }

        first, again = self._twice(reverse("public-habit-track"), line)

        self.assertEqual((first.status_code, again.status_code), (200, 200))
        self.assertEqual(
            sorted(HabitTracked.objects.values_list("idempotency_key", flat=True)),
            [f"{KEY}:0", f"{KEY}:1"],
        )

    def test_a_habit_key_too_long_is_refused(self):
        response = self._post(
            reverse("public-habit-track"),
            {"text": "#workout", "idempotency_key": "k" * 61},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(HabitTracked.objects.exists())

    def test_a_key_too_long_is_refused(self):
        response = self._post(
            "/journal/",
            {
                "comment": "x",
                "thread": "Daily",
                "tags": [],
                "idempotency_key": "k" * 65,
            },
        )

        self.assertEqual(response.status_code, 400)
