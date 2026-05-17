from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..models import Habit, HabitKeyword, HabitTracked, Thread


class TrackHabitAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.daily_thread = Thread.objects.create(name="Daily")
        cls.habit = Habit.objects.create(name="Health metrics", slug="health-metrics")
        HabitKeyword.objects.create(habit=cls.habit, keyword="health-metrics")
        cls.url = reverse("track-habit-api")

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _payload(self, **overrides):
        body = {
            "keyword": "health-metrics",
            "date": "2026-05-17",
            "note": "steps=8500 distance=6.2km active=42min",
        }
        body.update(overrides)
        return body

    def test_happy_path_creates_habit_tracked(self):
        self._auth()
        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"ok": True})

        events = HabitTracked.objects.filter(habit=self.habit)
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.note, "steps=8500 distance=6.2km active=42min")
        self.assertTrue(event.occured)
        self.assertEqual(event.thread, self.daily_thread)
        self.assertEqual(event.published.date().isoformat(), "2026-05-17")
        self.assertEqual(event.event_stream_id, self.habit.event_stream_id)

    def test_repost_same_day_is_idempotent_and_updates_note(self):
        self._auth()
        self.client.post(self.url, self._payload(note="steps=100"), format="json")
        self.client.post(self.url, self._payload(note="steps=8500"), format="json")

        events = HabitTracked.objects.filter(
            habit=self.habit, published__date="2026-05-17"
        )
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().note, "steps=8500")

    def test_missing_token_returns_401(self):
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(HabitTracked.objects.count(), 0)

    def test_bad_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
        response = self.client.post(self.url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_keyword_returns_404(self):
        self._auth()
        response = self.client.post(
            self.url, self._payload(keyword="does-not-exist"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(HabitTracked.objects.count(), 0)

    def test_resolves_habit_via_alternate_keyword(self):
        HabitKeyword.objects.create(habit=self.habit, keyword="hm")
        self._auth()
        response = self.client.post(
            self.url, self._payload(keyword="hm"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(HabitTracked.objects.get().habit, self.habit)

    def test_missing_date_returns_400(self):
        self._auth()
        payload = self._payload()
        del payload["date"]
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("date", response.json())

    def test_blank_note_is_allowed(self):
        self._auth()
        payload = self._payload()
        del payload["note"]
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(HabitTracked.objects.get().note, "")
