from datetime import datetime as datetime_cls
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ..models import HabitTracked, JournalAdded, Profile, Story, StoryEvent, Thread
from ..services.trips import (
    StoryNotFoundError,
    StoryStoppedError,
    add_trip_note,
    get_detail,
    list_active,
    list_history,
    start_trip,
    stop_trip,
    update_trip,
)


class TripServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")
        Profile.objects.create(user=cls.alice, default_board_thread=cls.daily)
        Profile.objects.create(user=cls.bob, default_board_thread=cls.daily)

    def test_start_trip_generates_default_title_when_blank(self):
        story = start_trip(self.alice, title=None)
        self.assertTrue(story.title.startswith("Trip "))
        self.assertEqual(story.user, self.alice)
        self.assertEqual(story.type, Story.Type.TRIP)
        self.assertIsNone(story.stopped)

    def test_start_trip_respects_user_title(self):
        story = start_trip(self.alice, title="Lisbon weekend")
        self.assertEqual(story.title, "Lisbon weekend")

    def test_stop_trip_sets_stopped_and_is_idempotent(self):
        story = start_trip(self.alice)
        stopped = stop_trip(self.alice, story.pk)
        self.assertIsNotNone(stopped.stopped)
        first_stop = stopped.stopped
        stop_trip(self.alice, story.pk)
        stopped.refresh_from_db()
        self.assertEqual(stopped.stopped, first_stop)

    def test_stop_trip_other_user_raises(self):
        story = start_trip(self.alice)
        with self.assertRaises(StoryNotFoundError):
            stop_trip(self.bob, story.pk)

    def test_update_trip_renames(self):
        story = start_trip(self.alice, title="A")
        updated = update_trip(self.alice, story.pk, title="B")
        self.assertEqual(updated.title, "B")

    def test_update_trip_other_user_raises(self):
        story = start_trip(self.alice)
        with self.assertRaises(StoryNotFoundError):
            update_trip(self.bob, story.pk, title="hijack")

    def test_add_trip_note_attaches_journal(self):
        story = start_trip(self.alice)
        published = timezone.now()
        journal = add_trip_note(
            self.alice, story.pk, comment="just walking around", published=published
        )
        self.assertEqual(journal.comment, "just walking around")
        link = StoryEvent.objects.get(story=story, event=journal)
        self.assertIsNotNone(link)

    def test_add_trip_note_with_poi_creates_habittracked_linked_to_story(self):
        story = start_trip(self.alice)
        comment = "#poi lat=40.7128 lng=-74.0060\nCoffee at the corner"
        journal = add_trip_note(
            self.alice, story.pk, comment=comment, published=timezone.now()
        )
        habits = HabitTracked.objects.filter(habit__slug="poi")
        self.assertEqual(habits.count(), 1)
        habit_event = habits.first()
        self.assertIn("lat=40.7128", habit_event.note)
        self.assertIn("lng=-74.0060", habit_event.note)
        # both events linked
        self.assertTrue(StoryEvent.objects.filter(story=story, event=journal).exists())
        self.assertTrue(
            StoryEvent.objects.filter(story=story, event=habit_event).exists()
        )

    def test_add_trip_note_on_stopped_story_raises(self):
        story = start_trip(self.alice)
        stop_trip(self.alice, story.pk)
        with self.assertRaises(StoryStoppedError):
            add_trip_note(
                self.alice, story.pk, comment="late", published=timezone.now()
            )

    def test_add_trip_note_other_user_raises(self):
        story = start_trip(self.alice)
        with self.assertRaises(StoryNotFoundError):
            add_trip_note(self.bob, story.pk, comment="ha", published=timezone.now())

    def test_list_active_returns_only_users_active_trips(self):
        a1 = start_trip(self.alice)
        a2 = start_trip(self.alice)
        stop_trip(self.alice, a1.pk)
        start_trip(self.bob)  # another user's trip should not appear
        active = list_active(self.alice)
        self.assertEqual([s.pk for s in active], [a2.pk])

    def test_list_history_pagination(self):
        stops = []
        for i in range(5):
            s = start_trip(self.alice, title=f"trip {i}")
            stop_trip(self.alice, s.pk)
            stops.append(s.pk)

        page1, total = list_history(self.alice, page=1, page_size=2)
        page2, _ = list_history(self.alice, page=2, page_size=2)
        page3, _ = list_history(self.alice, page=3, page_size=2)
        self.assertEqual(total, 5)
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertEqual(len(page3), 1)
        # latest-stop-first ordering: page 1 includes the latest two stops.
        latest_two = sorted(stops[-2:])
        self.assertEqual(sorted(s.pk for s in page1), latest_two)

    def test_get_detail_returns_journal_events_chronologically(self):
        story = start_trip(self.alice)
        t1 = datetime_cls(2026, 5, 25, 10, 0, tzinfo=dt_timezone.utc)
        t2 = datetime_cls(2026, 5, 25, 11, 0, tzinfo=dt_timezone.utc)
        t3 = datetime_cls(2026, 5, 25, 12, 0, tzinfo=dt_timezone.utc)
        add_trip_note(self.alice, story.pk, comment="later", published=t3)
        add_trip_note(
            self.alice,
            story.pk,
            comment="#poi lat=1 lng=2\nfirst location",
            published=t1,
        )
        add_trip_note(self.alice, story.pk, comment="middle", published=t2)
        detail_story, events = get_detail(self.alice, story.pk)
        self.assertEqual(detail_story.pk, story.pk)
        timestamps = [e["published"] for e in events]
        self.assertEqual(timestamps, sorted(timestamps))
        # Three notes were posted; the #poi hashtag also created a
        # HabitTracked linked to the story, but the detail view
        # intentionally omits non-journal events.
        self.assertEqual(len(events), 3)
        self.assertTrue(all(e["type"] == "journal" for e in events))

    def test_get_detail_other_user_raises(self):
        story = start_trip(self.alice)
        with self.assertRaises(StoryNotFoundError):
            get_detail(self.bob, story.pk)
