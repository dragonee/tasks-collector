"""Completing a task: the event, where it shows, and taking it back."""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from ..models import (
    Event,
    JournalAdded,
    Reflection,
    ReflectionLine,
    Task,
    TaskCompleted,
    Thread,
)
from ..services.tasks import documents
from ..services.tasks.base import create_task
from ..services.tasks.operations import complete, reopen
from ..services.trips import start_trip
from .factories import make_profile, make_thread, trip_links


class CompleteTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.daily(cls.user)
        cls.inbox = make_thread(cls.user, "Inbox")
        make_profile(cls.user, default_board_thread=cls.inbox)
        cls.day = datetime.date(2026, 11, 11)
        cls.at = timezone.make_aware(datetime.datetime(2026, 11, 11, 21, 30))

    def test_the_event_is_in_the_stream_and_thread_of_the_tasks_board(self):
        task = create_task(self.user, "call bank")

        completion = complete(task, self.user, day=self.day, at=self.at)

        self.assertEqual(completion.event_stream_id, self.inbox.board_stream_id)
        self.assertEqual(completion.thread, self.inbox)
        self.assertEqual(completion.created_by, self.user)
        self.assertEqual((completion.day, completion.published), (self.day, self.at))
        self.assertEqual(str(completion), "call bank")
        self.assertIn(completion, Event.objects.owned_by(self.user))

    def test_once_per_idempotency_key(self):
        task = create_task(self.user, "Do x (3)")

        first = complete(task, self.user, day=self.day, idempotency_key="tap-1")
        again = complete(task, self.user, day=self.day, idempotency_key="tap-1")
        other = complete(task, self.user, day=self.day, idempotency_key="tap-2")

        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        task.refresh_from_db()
        self.assertEqual(task.done_count, 2)
        reflection = Reflection.objects.get(thread=self.daily, pub_date=self.day)
        self.assertEqual(reflection.good, "Do x (1)\nDo x (2)")

    def test_the_mark_decides_the_field(self):
        for mark, field in ((None, "good"), ("~", "better"), ("^", "best")):
            with self.subTest(mark=mark):
                task = create_task(self.user, f"task {field}")

                complete(task, self.user, day=self.day, mark=mark)

                line = ReflectionLine.objects.get(task=task)
                self.assertEqual(line.field, field)

    def test_a_note_makes_a_journal_entry_of_the_completion(self):
        task = create_task(self.user, "call bank")
        trip = start_trip(self.user, title="Away")

        completion = complete(
            task, self.user, day=self.day, at=self.at, note="sorted", story=trip
        )

        journal = JournalAdded.objects.get()
        self.assertEqual(completion.journal, journal)
        self.assertEqual(journal.comment, "- [x] call bank\nsorted")
        self.assertEqual(journal.thread, self.daily)
        self.assertEqual(journal.published, self.at)
        self.assertTrue(trip_links(story=trip, event=journal).exists())
        # The "[x]" of the entry did not complete the task a second time.
        self.assertEqual(TaskCompleted.objects.count(), 1)

    def test_reopen_takes_back_the_last_step(self):
        task = create_task(self.user, "Do x (2)")
        complete(task, self.user, day=self.day)
        complete(task, self.user, day=self.day)

        self.assertTrue(reopen(task))

        task.refresh_from_db()
        self.assertEqual((task.done_count, task.completed_at), (1, None))
        self.assertEqual(TaskCompleted.objects.count(), 1)
        reflection = Reflection.objects.get(thread=self.daily, pub_date=self.day)
        self.assertEqual(reflection.good, "Do x (1)")

        self.assertTrue(reopen(task))
        self.assertFalse(reopen(task))

    def test_reopen_of_a_task_done_before_completions_were_events(self):
        # As the backfill leaves it: done, its reflection line linked, no
        # event.
        task = create_task(self.user, "call bank")
        task.done_count = 1
        task.completed_at = self.at
        task.save()
        reflection = documents.reflection_for(self.daily, self.day, create=True)
        documents.append_reflection_line(reflection, "good", "call bank", task=task)
        documents.append_reflection_line(reflection, "good", "slept well")

        self.assertTrue(reopen(task))

        task.refresh_from_db()
        self.assertFalse(task.done)
        reflection.refresh_from_db()
        self.assertEqual(reflection.good, "slept well")

    def test_deleting_the_user_takes_their_tasks_along(self):
        other = get_user_model().objects.create_user(username="gone", password="x")
        task = create_task(other, "theirs")
        complete(task, other, day=self.day)

        other.delete()

        self.assertFalse(Task.objects.filter(pk=task.pk).exists())
        self.assertFalse(TaskCompleted.objects.exists())


class CompletionOnPagesTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(username="u", password="x")
        cls.now = timezone.now()
        cls.day = timezone.localdate(cls.now)
        task = create_task(cls.user, "call the bank")
        cls.completion = complete(task, cls.user, day=cls.day, at=cls.now)

    def setUp(self):
        self.client.force_login(self.user)

    def test_the_event_archive_shows_it(self):
        response = self.client.get(reverse("public-event-archive-current-month"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "call the bank")

    def test_daily_events_leave_it_out(self):
        # Clients of this endpoint know a closed set of event types.
        response = self.client.get(
            "/api/events/daily/", {"date": self.day.isoformat(), "thread": "Daily"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["events"], [])
        self.assertEqual(response.json()["reflection"]["good"], "call the bank")

    def test_the_admin_lists_it(self):
        # The list of all events names each by its kind.
        for url, text in (
            ("/admin/tree/event/", "TaskCompleted"),
            ("/admin/tree/taskcompleted/", "call the bank"),
            ("/admin/tree/task/", "call the bank"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, text)
