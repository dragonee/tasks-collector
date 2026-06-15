import datetime

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..models import Habit, HabitTracked, Thread
from ..services.health import parse_weight_kg


class ParseWeightKgTestCase(APITestCase):
    def test_parses_decimal_value(self):
        self.assertEqual(parse_weight_kg("weight=82.5kg"), 82.5)

    def test_parses_integer_value(self):
        self.assertEqual(parse_weight_kg("#weight weight=80kg"), 80.0)

    def test_tolerates_space_before_unit(self):
        self.assertEqual(parse_weight_kg("weight=75.0 kg"), 75.0)

    def test_returns_none_when_absent(self):
        self.assertIsNone(parse_weight_kg("steps=8500 distance=6.2km"))

    def test_returns_none_for_empty(self):
        self.assertIsNone(parse_weight_kg(""))
        self.assertIsNone(parse_weight_kg(None))


class AndroidHealthDataAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.daily_thread = Thread.objects.create(name="Daily")
        # Created by migration 0074_weight_habit; fetching it also asserts the
        # migration ran.
        cls.weight_habit = Habit.objects.get(slug="weight")
        cls.url = reverse("android-health-data")

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _record_weight(self, note, *, days_ago=0):
        published = timezone.now() - datetime.timedelta(days=days_ago)
        return HabitTracked.objects.create(
            habit=self.weight_habit,
            occured=True,
            note=note,
            thread=self.daily_thread,
            published=published,
        )

    def test_returns_nulls_when_no_weight_recorded(self):
        self._auth()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"weight_kg": None, "recorded_at": None})

    def test_returns_latest_weight_and_date(self):
        event = self._record_weight("#weight weight=82.5kg")
        self._auth()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["weight_kg"], 82.5)
        self.assertEqual(body["recorded_at"], event.published.isoformat())

    def test_picks_most_recent_by_published(self):
        self._record_weight("#weight weight=80.0kg", days_ago=3)
        self._record_weight("#weight weight=81.0kg", days_ago=1)
        latest = self._record_weight("#weight weight=82.5kg", days_ago=0)
        self._auth()
        response = self.client.get(self.url)
        self.assertEqual(response.json()["weight_kg"], 82.5)
        self.assertEqual(response.json()["recorded_at"], latest.published.isoformat())

    def test_ignores_records_under_other_habits(self):
        other = Habit.objects.create(name="Health metrics", slug="health-metrics")
        HabitTracked.objects.create(
            habit=other,
            occured=True,
            note="weight=99.9kg",  # not the weight habit; must be ignored
            thread=self.daily_thread,
            published=timezone.now(),
        )
        self._auth()
        response = self.client.get(self.url)
        self.assertEqual(response.json(), {"weight_kg": None, "recorded_at": None})

    def test_skips_weight_records_without_parseable_note(self):
        # A newer weight event with no parseable value must fall through to the
        # most recent one that does.
        self._record_weight("#weight weight=70.0kg", days_ago=1)
        self._record_weight("#weight forgot the number", days_ago=0)
        self._auth()
        response = self.client.get(self.url)
        self.assertEqual(response.json()["weight_kg"], 70.0)

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_track_habit_text_then_read_back(self):
        # End-to-end over the real endpoints the Android client uses: post a
        # weight line through the non-idempotent text endpoint, then read it
        # back via the health-data endpoint.
        self._auth()
        post = self.client.post(
            reverse("public-habit-track"),
            {
                "text": "#weight weight=82.5kg",
                "published": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(post.status_code, status.HTTP_200_OK)
        self.assertEqual(
            HabitTracked.objects.filter(habit=self.weight_habit).count(), 1
        )

        response = self.client.get(self.url)
        self.assertEqual(response.json()["weight_kg"], 82.5)
