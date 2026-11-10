"""Streams are rows: created with what they are about, owned by its user,
and an event's stream follows from what the event is about."""

import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from ..models import (
    BoardCommitted,
    Breakthrough,
    EventStream,
    EventStreamAccess,
    HabitTracked,
    JournalAdded,
    Observation,
    ObservationAttached,
    ObservationType,
    ObservationUpdated,
    PhotoAdded,
    ProjectedOutcome,
    Thread,
)
from .factories import make_habit, make_thread

User = get_user_model()


def owner_of(stream):
    return stream.access.get(role=EventStreamAccess.Role.OWNER).user


class StreamsAreCreatedWithTheirSubjectTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="u", password="x")
        cls.other = User.objects.create_user(username="o", password="x")

    def test_each_thread_gets_its_own_board_and_journal_stream(self):
        daily = Thread.objects.daily(self.user)

        self.assertEqual(daily.board_stream.type, EventStream.Type.BOARD)
        self.assertEqual(daily.journal_stream.type, EventStream.Type.JOURNAL)
        self.assertEqual(daily.journal_stream.created_by, self.user)
        self.assertEqual(owner_of(daily.journal_stream), self.user)
        self.assertNotEqual(
            daily.journal_stream, Thread.objects.daily(self.other).journal_stream
        )

    def test_observation_habit_and_outcome_get_owned_streams(self):
        observation = Observation.objects.create(
            user=self.user,
            thread=Thread.objects.daily(self.user),
            type=ObservationType.objects.create(name="Error", slug="error"),
            pub_date=datetime.date(2026, 11, 10),
        )
        habit = make_habit(self.user, "Food")
        outcome = ProjectedOutcome.objects.create(
            breakthrough=Breakthrough.objects.create(user=self.user, slug="2026"),
            name="Run",
            description="",
            resolved_by=datetime.date(2026, 12, 31),
        )

        for subject, type_ in (
            (observation, EventStream.Type.OBSERVATION),
            (habit, EventStream.Type.HABIT),
            (outcome, EventStream.Type.PROJECTED_OUTCOME),
        ):
            with self.subTest(type_):
                self.assertEqual(subject.event_stream.type, type_)
                self.assertEqual(owner_of(subject.event_stream), self.user)

    def test_a_stream_has_exactly_one_owner(self):
        stream = Thread.objects.daily(self.user).journal_stream

        with self.assertRaises(IntegrityError), transaction.atomic():
            EventStreamAccess.objects.create(
                stream=stream, user=self.other, role=EventStreamAccess.Role.OWNER
            )

        EventStreamAccess.objects.create(
            stream=stream, user=self.other, role=EventStreamAccess.Role.VIEWER
        )


class EventsFollowTheirSubjectsStreamTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.daily(cls.user)
        cls.sidetrack = make_thread(cls.user, "Sidetrack")

    def test_journal_entries_and_photos_go_to_their_threads_journal(self):
        journal = JournalAdded.objects.create(thread=self.daily, comment="hello")
        photo = PhotoAdded.objects.create(
            thread=self.daily,
            comment="",
            original_key="k.jpg",
            content_type="image/jpeg",
        )

        self.assertEqual(journal.event_stream_id, self.daily.journal_stream_id)
        self.assertEqual(photo.event_stream_id, self.daily.journal_stream_id)

    def test_moving_an_entry_to_another_thread_moves_it_to_that_journal(self):
        journal = JournalAdded.objects.create(thread=self.daily, comment="hello")

        journal.thread = self.sidetrack
        journal.save()

        self.assertEqual(journal.event_stream_id, self.sidetrack.journal_stream_id)

    def test_board_commits_go_to_their_threads_board_stream(self):
        commit = BoardCommitted.objects.create(thread=self.daily, focus="")

        self.assertEqual(commit.event_stream_id, self.daily.board_stream_id)

    def test_tracked_habits_go_to_the_habits_stream(self):
        habit = make_habit(self.user, "Food")

        tracked = HabitTracked.objects.create(habit=habit, thread=self.daily)

        self.assertEqual(tracked.event_stream_id, habit.event_stream_id)

    def test_observation_updates_go_to_the_observation_and_take_its_thread(self):
        observation = Observation.objects.create(
            user=self.user,
            thread=self.sidetrack,
            type=ObservationType.objects.create(name="Error", slug="error"),
            pub_date=datetime.date(2026, 11, 10),
        )

        update = ObservationUpdated.objects.create(
            observation=observation, comment="later", published=timezone.now()
        )

        self.assertEqual(update.event_stream_id, observation.event_stream_id)
        self.assertEqual(update.thread, self.sidetrack)

    def test_outcome_events_go_to_the_outcomes_stream(self):
        outcome = ProjectedOutcome.objects.create(
            breakthrough=Breakthrough.objects.create(user=self.user, slug="2026"),
            name="Run",
            description="",
            resolved_by=datetime.date(2026, 12, 31),
        )

        made = outcome.projectedoutcomemade_set.get()

        self.assertEqual(made.event_stream_id, outcome.event_stream_id)

    def test_an_event_with_no_derivable_stream_needs_one_set(self):
        with self.assertRaisesMessage(ValueError, "needs an event_stream_id"):
            ObservationAttached.objects.create(
                thread=self.daily, other_event_stream_id=self.daily.journal_stream_id
            )
