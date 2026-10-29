"""observation-events/ is a read-only view of observation event streams.
Events are recorded by the observation endpoints; writing them here would
rewrite or drop stream history behind the Observation's back."""

from datetime import date

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import (
    Event,
    Observation,
    ObservationClosed,
    ObservationMade,
    ObservationType,
    Thread,
)

EVENTS_URL = "/observation-events/"


class ObservationEventAPIReadOnlyTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.thread = Thread.objects.create(name="Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")

        observation = Observation.objects.create(
            user=cls.user,
            thread=cls.thread,
            type=cls.type,
            pub_date=date(2026, 10, 20),
            situation="closed",
        )
        cls.made = ObservationMade.from_observation(observation)
        cls.made.save()
        cls.closed = ObservationClosed.from_observation(observation)
        cls.closed.save()
        observation.delete()

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_list_and_retrieve(self):
        resp = self.client.get(EVENTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {e["id"] for e in resp.json()["results"]}, {self.made.pk, self.closed.pk}
        )

        resp = self.client.get(f"{EVENTS_URL}{self.closed.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["resourcetype"], "ObservationClosed")

    def test_writes_are_not_allowed(self):
        payload = {"resourcetype": "ObservationMade", "situation": "rewritten"}
        detail = f"{EVENTS_URL}{self.made.pk}/"

        for method, url in [
            ("post", EVENTS_URL),
            ("put", detail),
            ("patch", detail),
            ("delete", f"{EVENTS_URL}{self.closed.pk}/"),
        ]:
            with self.subTest(method=method):
                resp = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        self.assertEqual(Event.objects.count(), 2)
        self.made.refresh_from_db()
        self.assertEqual(self.made.situation, "closed")
