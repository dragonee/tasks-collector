"""updates/ records an ObservationUpdated on an open observation's stream.
The CLI's `update` tool posts {"comment", "observation"} here."""

from datetime import date

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Observation, ObservationType, ObservationUpdated, Thread

UPDATES_URL = "/updates/"


class ObservationUpdatedAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.thread = Thread.objects.create(name="Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")
        cls.observation = Observation.objects.create(
            user=cls.user,
            thread=cls.thread,
            type=cls.type,
            pub_date=date(2026, 10, 20),
            situation="open",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_create_on_observation_joins_its_stream(self):
        resp = self.client.post(
            UPDATES_URL,
            {"comment": "progress", "observation": self.observation.pk},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["observation"], self.observation.pk)

        update = ObservationUpdated.objects.get()
        self.assertEqual(update.event_stream_id, self.observation.event_stream_id)
        self.assertEqual(update.thread, self.thread)

    def test_create_without_observation_returns_400(self):
        for data in [{"comment": "orphan"}, {"comment": "orphan", "observation": None}]:
            with self.subTest(data=data):
                resp = self.client.post(UPDATES_URL, data, format="json")

                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("observation", resp.json())

        self.assertFalse(ObservationUpdated.objects.exists())

    def test_create_on_closed_observation_returns_400(self):
        pk = self.observation.pk
        self.observation.delete()

        resp = self.client.post(
            UPDATES_URL, {"comment": "late", "observation": pk}, format="json"
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("observation", resp.json())
