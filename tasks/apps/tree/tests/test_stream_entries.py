"""An event is a member of its home stream and of any stream it is added to:
a trip note lives in its thread's journal and in the trip."""

import io
import threading

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.models.signals import post_save
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from ..models import (
    EventStream,
    EventStreamAccess,
    EventStreamEntry,
    JournalAdded,
    Story,
    Thread,
)
from ..services.trips import add_trip_note, start_trip
from .factories import make_thread

User = get_user_model()


def member_streams(event):
    return set(event.stream_entries.values_list("stream_id", flat=True))


class HomeEntryTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.daily(cls.user)
        cls.sidetrack = make_thread(cls.user, "Sidetrack")

    def test_a_new_event_is_a_member_of_its_home_stream(self):
        journal = JournalAdded.objects.create(thread=self.daily, comment="hello")

        self.assertEqual(member_streams(journal), {self.daily.journal_stream_id})

    def test_saving_again_adds_nothing(self):
        journal = JournalAdded.objects.create(thread=self.daily, comment="hello")

        journal.comment = "hello again"
        journal.save()

        self.assertEqual(journal.stream_entries.count(), 1)

    def test_membership_follows_a_changed_home_and_keeps_the_trip(self):
        story = start_trip(self.user)
        journal = add_trip_note(self.user, story.pk, "walking", timezone.now())

        journal = JournalAdded.objects.get(pk=journal.pk)
        journal.thread = self.sidetrack
        journal.save()

        self.assertEqual(
            member_streams(journal),
            {self.sidetrack.journal_stream_id, story.event_stream_id},
        )


class TripStreamsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="u", password="x")

    def test_a_trip_gets_its_own_stream_owned_by_the_traveller(self):
        story = start_trip(self.user)

        self.assertEqual(story.event_stream.type, EventStream.Type.TRIP)
        self.assertEqual(
            story.event_stream.access.get(role=EventStreamAccess.Role.OWNER).user,
            self.user,
        )

    def test_a_trip_note_is_in_the_journal_and_the_trip(self):
        story = start_trip(self.user)

        journal = add_trip_note(self.user, story.pk, "walking", timezone.now())

        self.assertEqual(
            member_streams(journal),
            {Thread.objects.daily(self.user).journal_stream_id, story.event_stream_id},
        )
        self.assertEqual(journal.trip, story)

    def test_adding_to_the_same_trip_again_changes_nothing(self):
        story = start_trip(self.user)
        journal = add_trip_note(self.user, story.pk, "walking", timezone.now())

        story.add(journal)

        self.assertEqual(journal.stream_entries.count(), 2)

    def test_an_event_belongs_to_one_trip_at_most(self):
        first, second = start_trip(self.user), start_trip(self.user)
        journal = add_trip_note(self.user, first.pk, "walking", timezone.now())

        with self.assertRaisesMessage(ValueError, "another trip"):
            second.add(journal)

    def test_trip_is_none_outside_trips_and_prefetches_in_one_query(self):
        daily = Thread.objects.daily(self.user)
        story = start_trip(self.user)
        add_trip_note(self.user, story.pk, "on the way", timezone.now())
        JournalAdded.objects.create(thread=daily, comment="at home")

        with self.assertNumQueries(2):
            entries = list(
                JournalAdded.objects.prefetch_related(JournalAdded.prefetch_trip())
            )
            trips = {entry.comment: entry.trip for entry in entries}

        self.assertEqual(trips, {"on the way": story, "at home": None})

    def test_deleting_a_trips_user_deletes_the_trip_and_its_stream(self):
        story = start_trip(self.user)
        stream_id = story.event_stream_id

        self.user.delete()

        self.assertFalse(Story.objects.filter(pk=story.pk).exists())
        self.assertFalse(EventStream.objects.filter(pk=stream_id).exists())


class ConcurrentTripAddTestCase(TransactionTestCase):
    """One event added to two trips at once: one of them gets it."""

    def setUp(self):
        user = User.objects.create_user(username="u", password="x")
        self.first, self.second = start_trip(user), start_trip(user)
        self.journal = JournalAdded.objects.create(
            thread=Thread.objects.daily(user), comment="walking"
        )

    def test_the_second_add_finds_the_first(self):
        first_saved = threading.Event()
        release_first = threading.Event()
        results = {}

        def hold_first_before_commit(sender, instance, **kwargs):
            if threading.current_thread().name == "first":
                first_saved.set()
                release_first.wait(timeout=5)

        def add(name, story):
            def run():
                try:
                    story.add(self.journal)
                    results[name] = "added"
                except ValueError as e:
                    results[name] = e
                finally:
                    connection.close()

            thread = threading.Thread(target=run, name=name)
            thread.start()
            return thread

        post_save.connect(hold_first_before_commit, sender=EventStreamEntry)
        try:
            first = add("first", self.first)
            self.assertTrue(first_saved.wait(timeout=5))

            # The first add has saved its entry but not committed. Give the
            # second one time to run as far as it can before letting go.
            second = add("second", self.second)
            second.join(timeout=0.5)
            release_first.set()

            first.join(timeout=5)
            second.join(timeout=5)
        finally:
            post_save.disconnect(hold_first_before_commit, sender=EventStreamEntry)

        self.assertEqual(results["first"], "added")
        self.assertIsInstance(results["second"], ValueError)
        self.assertEqual(
            EventStreamEntry.objects.filter(
                event=self.journal, stream__type=EventStream.Type.TRIP
            ).count(),
            1,
        )


class EnsureHomeEntriesTestCase(TestCase):
    def test_restores_missing_home_entries_and_nothing_else(self):
        user = User.objects.create_user(username="u", password="x")
        journal = JournalAdded.objects.create(
            thread=Thread.objects.daily(user), comment="hello"
        )
        EventStreamEntry.objects.filter(event=journal).delete()

        call_command("ensure_stream_entries", stdout=io.StringIO())
        call_command("ensure_stream_entries", stdout=io.StringIO())

        self.assertEqual(
            member_streams(journal), {Thread.objects.daily(user).journal_stream_id}
        )
