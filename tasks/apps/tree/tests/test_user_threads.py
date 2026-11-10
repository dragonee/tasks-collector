"""Threads and breakthroughs belong to a user.

Every user gets the built-in threads (Daily, Weekly, big-picture), a board on
each and a profile when the account is created. Code that names a thread
("Daily", ?thread=Weekly, the thread of a posted journal entry) means the
acting user's thread of that name, never someone else's.
"""

import datetime

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import ProtectedError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from ..board_operations import add_task_to_board
from ..models import (
    Board,
    Breakthrough,
    JournalAdded,
    Plan,
    Profile,
    ProjectedOutcome,
    Thread,
)
from ..services.breakthrough.operations import move_projected_outcome_to_next_year
from ..services.provisioning import provision_user
from ..services.trips import add_trip_note, start_trip
from .factories import make_thread
from .test_breakthrough_web import breakthrough_post_data

User = get_user_model()


class ProvisioningTestCase(TestCase):
    def test_new_user_gets_builtin_threads_boards_and_profile(self):
        user = User.objects.create_user(username="new", password="x")

        threads = Thread.objects.filter(user=user)
        self.assertEqual(
            sorted(threads.values_list("name", flat=True)),
            sorted(Thread.BUILTIN_NAMES),
        )
        for thread in threads:
            self.assertEqual(Board.objects.filter(thread=thread).count(), 1)
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_provisioning_twice_creates_nothing_new(self):
        user = User.objects.create_user(username="new", password="x")
        counts = (
            Thread.objects.count(),
            Board.objects.count(),
            Profile.objects.count(),
        )

        provision_user(user)

        self.assertEqual(
            (Thread.objects.count(), Board.objects.count(), Profile.objects.count()),
            counts,
        )

    def test_provisioning_restores_a_missing_builtin(self):
        user = User.objects.create_user(username="new", password="x")
        Thread.objects.filter(user=user, name=Thread.WEEKLY).update(name="Renamed")

        provision_user(user)

        weekly = Thread.objects.get(user=user, name=Thread.WEEKLY)
        self.assertTrue(Board.objects.filter(thread=weekly).exists())

    def test_users_have_separate_threads_of_the_same_name(self):
        alice = User.objects.create_user(username="alice", password="x")
        bob = User.objects.create_user(username="bob", password="x")

        self.assertNotEqual(Thread.objects.daily(alice), Thread.objects.daily(bob))


class BuiltinThreadProtectionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="u", password="x")

    # The refusal aborts the delete's transaction, hence the atomic blocks.

    def test_builtin_thread_cannot_be_deleted(self):
        daily = Thread.objects.daily(self.user)

        with self.assertRaises(ProtectedError), transaction.atomic():
            daily.delete()

        self.assertTrue(Thread.objects.filter(pk=daily.pk).exists())

    def test_builtin_threads_cannot_be_deleted_in_bulk(self):
        with self.assertRaises(ProtectedError), transaction.atomic():
            Thread.objects.filter(user=self.user).delete()

        self.assertEqual(Thread.objects.filter(user=self.user).count(), 3)

    def test_other_threads_can_be_deleted(self):
        sidetrack = make_thread(self.user, "Sidetrack")

        sidetrack.delete()

        self.assertFalse(Thread.objects.filter(pk=sidetrack.pk).exists())

    def test_builtin_threads_go_with_their_user(self):
        user = User.objects.create_user(username="leaving", password="x")

        user.delete()

        self.assertFalse(Thread.objects.filter(user_id=user.pk).exists())

    def test_admin_offers_no_delete_for_builtin_threads(self):
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser(username="admin", password="x")
        thread_admin = admin.site._registry[Thread]

        self.assertFalse(
            thread_admin.has_delete_permission(request, Thread.objects.daily(self.user))
        )
        self.assertTrue(
            thread_admin.has_delete_permission(
                request, make_thread(self.user, "Sidetrack")
            )
        )


class ThreadNamesAreThePerUserTestCase(APITestCase):
    """A thread name in a request resolves among the caller's threads."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")

    def setUp(self):
        self.client.force_authenticate(user=self.bob)

    def test_posted_journal_entry_lands_in_the_callers_thread(self):
        response = self.client.post(
            "/journal/",
            {"comment": "hello", "thread": "Daily", "tags": []},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        journal = JournalAdded.objects.get(pk=response.json()["id"])
        self.assertEqual(journal.thread, Thread.objects.daily(self.bob))

    def test_unknown_thread_name_is_rejected(self):
        make_thread(self.alice, "Alices-only")

        response = self.client.post(
            "/journal/",
            {"comment": "hello", "thread": "Alices-only", "tags": []},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plan_thread_filter_returns_only_the_callers_plans(self):
        day = datetime.date(2026, 11, 15)
        mine = Plan.objects.create(
            pub_date=day,
            thread=Thread.objects.get(user=self.bob, name=Thread.WEEKLY),
            focus="mine",
        )
        Plan.objects.create(
            pub_date=day,
            thread=Thread.objects.get(user=self.alice, name=Thread.WEEKLY),
            focus="theirs",
        )

        response = self.client.get("/plans/", {"thread": "Weekly"})

        self.assertEqual([p["id"] for p in response.json()["results"]], [mine.pk])

    def test_board_append_by_thread_name_uses_the_callers_board(self):
        board = add_task_to_board(self.bob, "buy milk", Thread.WEEKLY)

        self.assertEqual(board.thread, Thread.objects.get(user=self.bob, name="Weekly"))
        alices = Board.objects.get(thread__user=self.alice, thread__name="Weekly")
        self.assertEqual(alices.state, [])

    def test_trip_note_lands_in_the_travellers_daily_thread(self):
        story = start_trip(self.bob)

        journal = add_trip_note(
            self.bob, story.pk, comment="walking", published=timezone.now()
        )

        self.assertEqual(journal.thread, Thread.objects.daily(self.bob))

    def test_today_page_lists_and_opens_only_own_threads(self):
        self.client.force_login(self.bob)
        make_thread(self.alice, "Alices-only")

        response = self.client.get("/", {"thread": "Daily"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context["thread"], Thread.objects.daily(self.bob))
        self.assertEqual(
            {t.user_id for t in response.context["threads"]}, {self.bob.pk}
        )
        response = self.client.get("/", {"thread": "Alices-only"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BreakthroughPerUserTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")

    def test_each_user_has_their_own_year(self):
        Breakthrough.objects.create(user=self.alice, slug="2026", theme="Alice's")
        self.client.force_login(self.bob)

        response = self.client.post(
            "/breakthrough/2026/", breakthrough_post_data(theme="Bob's")
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Breakthrough.objects.get(user=self.alice, slug="2026").theme, "Alice's"
        )
        self.assertEqual(
            Breakthrough.objects.get(user=self.bob, slug="2026").theme, "Bob's"
        )

    def test_outcome_events_are_filed_under_the_owners_daily_thread(self):
        breakthrough = Breakthrough.objects.create(user=self.bob, slug="2026")

        outcome = ProjectedOutcome.objects.create(
            breakthrough=breakthrough,
            name="Run",
            description="",
            resolved_by=datetime.date(2026, 12, 31),
        )

        made = outcome.projectedoutcomemade_set.get()
        self.assertEqual(made.thread, Thread.objects.daily(self.bob))

    def test_moving_to_next_year_stays_with_the_owner(self):
        Breakthrough.objects.create(user=self.alice, slug="2027")
        outcome = ProjectedOutcome.objects.create(
            breakthrough=Breakthrough.objects.create(user=self.bob, slug="2026"),
            name="Run",
            description="",
            resolved_by=datetime.date(2026, 12, 31),
        )

        next_year = move_projected_outcome_to_next_year(outcome)

        self.assertEqual((next_year.user, next_year.slug), (self.bob, "2027"))
