"""Habits, habit keywords and statistics belong to a user.

A hashtag in a journal entry names the author's habit; habit slugs and
keywords are unique per user, so two people can both track #food. Every user
gets the built-in poi and weight habits the code itself records.
"""

import datetime
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Habit, HabitKeyword, HabitTracked, JournalAdded, Profile, Thread
from ..services.health import latest_weight
from ..services.journalling import process_journal_entry
from ..services.provisioning import BUILTIN_HABITS
from ..utils.statistics import get_aggregate_statistics, get_word_count_statistic
from .factories import make_habit, make_token

User = get_user_model()


class BuiltinHabitsTestCase(TestCase):
    def test_new_user_gets_the_builtin_habits_selected_in_their_profile(self):
        user = User.objects.create_user(username="new", password="x")

        for builtin in BUILTIN_HABITS:
            habit = Habit.objects.get(user=user, slug=builtin.slug)
            self.assertEqual(habit.get_keywords(), set(builtin.keywords))
        self.assertEqual(
            set(Profile.objects.get(user=user).habit_keywords.all()),
            set(HabitKeyword.objects.filter(user=user)),
        )

    def test_users_get_separate_builtin_habits(self):
        alice = User.objects.create_user(username="alice", password="x")
        bob = User.objects.create_user(username="bob", password="x")

        self.assertNotEqual(
            Habit.objects.get(user=alice, slug="poi"),
            Habit.objects.get(user=bob, slug="poi"),
        )


class HabitKeywordsPerUserTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")

    def test_two_users_can_track_the_same_hashtag(self):
        alices = make_habit(self.alice, "Food", keywords=["food"])
        bobs = make_habit(self.bob, "Food", keywords=["food"])

        for user, habit in ((self.alice, alices), (self.bob, bobs)):
            journal = JournalAdded.objects.create(
                thread=Thread.objects.daily(user),
                comment="#food pasta",
                published=timezone.now(),
            )
            process_journal_entry(journal)
            tracked = HabitTracked.objects.get(habit=habit)
            self.assertEqual(tracked.thread, Thread.objects.daily(user))

    def test_keyword_takes_its_owner_from_the_habit(self):
        habit = make_habit(self.alice, "Food", keywords=["food"])

        self.assertEqual(habit.keywords.get().user, self.alice)

    def test_new_keyword_is_selected_only_in_its_owners_profile(self):
        make_habit(self.alice, "Food", keywords=["food"])

        self.assertTrue(
            Profile.objects.get(user=self.alice)
            .habit_keywords.filter(keyword="food")
            .exists()
        )
        self.assertFalse(
            Profile.objects.get(user=self.bob)
            .habit_keywords.filter(keyword="food")
            .exists()
        )


class HabitEndpointsPerUserTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        cls.alices_food = make_habit(cls.alice, "Food", keywords=["food"])

    def setUp(self):
        self.client.force_authenticate(user=self.bob)

    def test_habit_list_shows_only_own_habits(self):
        response = self.client.get("/habit-api/")

        self.assertEqual(
            {h["id"] for h in response.json()["results"]},
            set(Habit.objects.filter(user=self.bob).values_list("id", flat=True)),
        )

    def test_created_habit_belongs_to_the_caller(self):
        response = self.client.post(
            "/habit-api/", {"name": "Food", "slug": "food"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Habit.objects.get(pk=response.json()["id"]).user, self.bob)

    def test_duplicate_own_slug_is_rejected(self):
        response = self.client.post(
            "/habit-api/", {"name": "Points", "slug": "poi"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_habit_page_is_found_by_own_slug_only(self):
        self.client.force_login(self.bob)

        response = self.client.get(reverse("public-habit-detail", args=["food"]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_keywords_endpoint_lists_only_own_keywords(self):
        response = self.client.get("/habit/keywords/mine/", {"all": "true"})

        self.assertEqual(
            {k["keyword"] for k in response.json()},
            set(
                HabitKeyword.objects.filter(user=self.bob).values_list(
                    "keyword", flat=True
                )
            ),
        )

    def test_track_api_does_not_resolve_someone_elses_keyword(self):
        token = make_token(self.bob)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.post(
            reverse("track-habit-api"),
            {"keyword": "food", "date": "2026-11-10", "note": "pasta"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(HabitTracked.objects.exists())


class LatestWeightPerUserTestCase(TestCase):
    def test_reads_only_the_users_own_weight(self):
        alice = User.objects.create_user(username="alice", password="x")
        bob = User.objects.create_user(username="bob", password="x")
        HabitTracked.objects.create(
            habit=Habit.objects.get(user=alice, slug="weight"),
            note="weight=70kg",
            thread=Thread.objects.daily(alice),
            published=timezone.now(),
        )

        self.assertEqual(latest_weight(alice).value_kg, 70.0)
        self.assertIsNone(latest_weight(bob))


class StatisticsPerUserTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        published = timezone.make_aware(datetime.datetime(2026, 11, 10, 12))
        JournalAdded.objects.create(
            thread=Thread.objects.daily(cls.alice),
            comment="one two three",
            published=published,
        )
        JournalAdded.objects.create(
            thread=Thread.objects.daily(cls.bob), comment="four", published=published
        )

    def test_counts_only_the_users_own_events(self):
        self.assertEqual(get_aggregate_statistics(self.alice)["journal_count"], 1)
        self.assertEqual(get_aggregate_statistics(self.bob)["journal_count"], 1)

    def test_word_counts_are_kept_per_user(self):
        call_command("update_word_count", stdout=io.StringIO())

        self.assertEqual(get_word_count_statistic(self.alice)[0], 3)
        self.assertEqual(get_word_count_statistic(self.bob)[0], 1)
        self.assertEqual(get_word_count_statistic(self.alice, year=2026)[0], 3)
