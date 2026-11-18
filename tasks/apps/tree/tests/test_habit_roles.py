"""What code finds a habit by: the role it fills for its user."""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Habit, HabitKeyword, HabitRole, HabitTracked, JournalAdded, Thread
from ..services.habits.roles import habit_for, habit_for_writing
from ..services.health import latest_weight
from .factories import make_habit, make_token

User = get_user_model()
Role = HabitRole.Role


class RolesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")

    def test_a_new_user_s_weight_habit_fills_the_weight_role(self):
        self.assertEqual(
            habit_for(self.user, Role.WEIGHT),
            Habit.objects.get(user=self.user, slug="weight"),
        )
        self.assertIsNone(habit_for(self.user, Role.BIKE_RIDE))

    def test_the_first_write_for_a_role_makes_its_habit(self):
        habit = habit_for_writing(self.user, Role.DAILY_HEALTH)

        self.assertEqual(habit.name, "Health")
        self.assertEqual(habit.get_keywords(), {"health-metrics"})
        self.assertEqual(
            list(habit.metrics.values_list("key", flat=True)),
            ["steps", "distance", "active", "kcal"],
        )
        self.assertEqual(habit_for_writing(self.user, Role.DAILY_HEALTH), habit)

    def test_a_made_habit_keeps_away_from_the_users_slugs_and_keywords(self):
        workout = make_habit(self.user, "Workout", keywords=["workout"])

        habit = habit_for_writing(self.user, Role.BIKE_RIDE)

        self.assertNotEqual(habit, workout)
        self.assertEqual(habit.slug, "workout-2")
        self.assertEqual(habit.get_keywords(), set())

    def test_a_habit_given_a_role_gets_the_metrics_it_writes(self):
        rides = make_habit(self.user, "Rides", keywords=["rides"])
        HabitRole.objects.create(role=Role.BIKE_RIDE, habit=rides)

        self.assertEqual(habit_for_writing(self.user, Role.BIKE_RIDE), rides)
        self.assertTrue(rides.metrics.filter(key="duration").exists())

    def test_roles_are_each_users_own(self):
        bob = User.objects.create_user(username="bob", password="x")
        self.assertNotEqual(
            habit_for(bob, Role.WEIGHT), habit_for(self.user, Role.WEIGHT)
        )

    def test_weight_is_read_from_the_habit_that_fills_the_role(self):
        scale = make_habit(self.user, "Scale", keywords=["scale"])
        HabitRole.objects.filter(user=self.user, role=Role.WEIGHT).update(habit=scale)
        HabitTracked.objects.create(
            habit=scale,
            note="#scale (weight=79.5kg)",
            thread=Thread.objects.daily(self.user),
            published=timezone.now(),
        )
        self.assertEqual(latest_weight(self.user), None)

        scale.metrics.create(key="weight", unit="kg", decimals=1)
        self.assertEqual(latest_weight(self.user).value_kg, 79.5)


class WriteByRoleAPITest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")
        cls.token = make_token(cls.user)

    def setUp(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _day(self, date, note, **body):
        return self.client.post(
            reverse("track-habit-api"),
            {"date": date, "note": note, **body},
            format="json",
        )

    def test_the_phone_s_day_goes_to_the_role_s_habit(self):
        response = self._day(
            "2026-11-18",
            "",
            role="daily-health",
            values={"steps": 5000, "distance": 3.5, "active": 80, "kcal": 2000},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = HabitTracked.objects.get(habit=habit_for(self.user, Role.DAILY_HEALTH))
        self.assertEqual(entry.note, "steps=5000 distance=3.5km active=80min kcal=2000")
        self.assertEqual(entry.role, Role.DAILY_HEALTH)

    def test_the_day_replaces_its_own_entry_not_one_typed_by_hand(self):
        self._day("2026-11-18", "steps=1", role="daily-health")
        habit = habit_for(self.user, Role.DAILY_HEALTH)
        by_hand = HabitTracked.objects.create(
            habit=habit,
            note="#health-metrics doctor",
            thread=Thread.objects.daily(self.user),
            published=timezone.make_aware(datetime.datetime(2026, 11, 18, 8)),
        )

        self._day("2026-11-18", "steps=2", role="daily-health")
        # An older phone, by keyword: the same role.
        self._day("2026-11-18", "steps=3", keyword="health-metrics")

        by_hand.refresh_from_db()
        self.assertEqual(by_hand.note, "#health-metrics doctor")
        self.assertEqual(
            list(
                HabitTracked.objects.filter(
                    habit=habit, role=Role.DAILY_HEALTH
                ).values_list("note", flat=True)
            ),
            ["steps=3"],
        )

    def test_the_habit_s_other_keywords_leave_the_role_s_entry_alone(self):
        self._day("2026-11-18", "steps=1", role="daily-health")
        habit = habit_for(self.user, Role.DAILY_HEALTH)
        HabitKeyword.objects.create(habit=habit, keyword="health")

        # What the Today screen's habit dialog sends.
        self._day("2026-11-18", "doctor", keyword="health")
        self._day("2026-11-18", "steps=2", role="daily-health")

        self.assertEqual(
            sorted(
                HabitTracked.objects.filter(habit=habit).values_list("note", "role")
            ),
            [("doctor", ""), ("steps=2", Role.DAILY_HEALTH)],
        )

    def test_a_ride_is_a_new_entry_of_the_role_s_habit_each_time(self):
        url = reverse("habit-tracked-create")
        body = {
            "role": "bike-ride",
            "note": "Bike ride",
            "values": {"duration": 2700},
            "published": "2026-11-18T07:30:00+01:00",
            "idempotency_key": "bike-ride:abc",
        }
        first = self.client.post(url, body, format="json")
        again = self.client.post(url, body, format="json")
        other = self.client.post(
            url, {**body, "idempotency_key": "bike-ride:def"}, format="json"
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.json()["note"], "Bike ride (duration=45m)")
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(other.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            HabitTracked.objects.filter(
                habit=habit_for(self.user, Role.BIKE_RIDE), role=Role.BIKE_RIDE
            ).count(),
            2,
        )

    def test_an_unknown_role_is_refused(self):
        response = self.client.post(
            reverse("habit-tracked-create"), {"role": "sleep"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_write_names_a_keyword_or_a_role(self):
        response = self.client.post(
            reverse("habit-tracked-create"), {"note": "x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_habits_say_which_roles_they_fill(self):
        response = self.client.get(reverse("my-habit-keywords"), {"all": "true"})
        weight = next(item for item in response.json() if item["keyword"] == "weight")
        self.assertEqual(weight["habit"]["roles"], ["weight"])


class BreakthroughByRoleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")
        cls.entry = JournalAdded.objects.create(
            thread=Thread.objects.daily(cls.user),
            comment="A good day",
            published=timezone.make_aware(datetime.datetime(2025, 6, 1, 12)),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _breakthrough(self, text):
        return self.client.post(
            reverse("public-habit-track") + "?form=only_text",
            {"text": text, "journal": self.entry.pk, "role": "breakthrough"},
            HTTP_HX_REQUEST="true",
        )

    def test_the_button_writes_to_the_role_s_habit_without_a_hashtag(self):
        response = self._breakthrough("Spoke at a conference")

        self.assertEqual(response.status_code, 200)
        habit = habit_for(self.user, Role.BREAKTHROUGH)
        tracked = HabitTracked.objects.get(habit=habit)
        self.assertEqual(tracked.note, "Spoke at a conference")
        self.assertEqual(tracked.published, self.entry.published)

    def test_the_page_shows_the_role_s_habit_whatever_its_slug(self):
        self._breakthrough("Spoke at a conference")
        habit = habit_for(self.user, Role.BREAKTHROUGH)
        habit.slug = "przelom"
        habit.save()

        page = self.client.get(reverse("breakthrough", args=[2026]) + "?review=0")
        self.assertContains(page, "Spoke at a conference")


class RolesSettingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")
        cls.rides = make_habit(cls.user, "Rides", keywords=["rides"])

    def setUp(self):
        self.client.force_login(self.user)

    def test_a_role_goes_to_the_habit_chosen_and_one_left_empty_is_emptied(self):
        weight = habit_for(self.user, Role.WEIGHT)
        response = self.client.post(
            reverse("settings-habits"),
            {"role_bike_ride": self.rides.pk, "role_weight": ""},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(habit_for(self.user, Role.BIKE_RIDE), self.rides)
        self.assertTrue(self.rides.metrics.filter(key="duration").exists())
        self.assertIsNone(habit_for(self.user, Role.WEIGHT))
        self.assertTrue(Habit.objects.filter(pk=weight.pk).exists())

    def test_someone_elses_habit_cannot_be_chosen(self):
        bob = User.objects.create_user(username="bob", password="x")
        theirs = make_habit(bob, "Theirs", keywords=["theirs"])
        response = self.client.post(
            reverse("settings-habits"), {"role_bike_ride": theirs.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(habit_for(self.user, Role.BIKE_RIDE))
