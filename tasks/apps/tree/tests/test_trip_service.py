import io
import uuid
from datetime import datetime as datetime_cls
from datetime import timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from PIL import Image

from ..models import (
    HabitTracked,
    JournalAdded,
    PhotoAdded,
    Profile,
    SharedStory,
    Story,
    StoryEvent,
    Thread,
)
from ..services.trips import (
    PhotoObjectMissingError,
    StoryNotFoundError,
    StoryStoppedError,
    add_trip_note,
    add_trip_photo,
    get_detail,
    get_shared_story,
    list_active,
    list_history,
    presign_photo_original,
    presign_photo_upload,
    share_trip,
    start_trip,
    stop_trip,
    unshare_trip,
    update_trip,
)

STORAGE = "tasks.apps.tree.services.photos.storage"


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

    def test_add_trip_note_uses_daily_thread_not_board_default(self):
        # Diary-style trip notes always land on the Daily thread, even when the
        # user's default *board* thread is something else (e.g. the Inbox).
        inbox, _ = Thread.objects.get_or_create(name="Inbox")
        Profile.objects.filter(user=self.alice).update(default_board_thread=inbox)
        story = start_trip(self.alice)
        journal = add_trip_note(
            self.alice, story.pk, comment="walking", published=timezone.now()
        )
        self.assertEqual(journal.thread, self.daily)

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

    def test_add_trip_note_idempotency_returns_same_note(self):
        # A retried note carrying the same key creates exactly one event.
        story = start_trip(self.alice)
        published = timezone.now()
        first = add_trip_note(
            self.alice,
            story.pk,
            comment="walk",
            published=published,
            idempotency_key="note-key-1",
        )
        second = add_trip_note(
            self.alice,
            story.pk,
            comment="walk",
            published=published,
            idempotency_key="note-key-1",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            JournalAdded.objects.filter(idempotency_key="note-key-1").count(), 1
        )
        self.assertEqual(StoryEvent.objects.filter(story=story, event=first).count(), 1)

    def test_add_trip_note_idempotent_retry_succeeds_after_stop(self):
        # The first call's response was lost, the trip was then stopped, and the
        # outbox retries: the dedup lookup precedes the stopped check, so the
        # retry returns the original note instead of raising StoryStoppedError.
        story = start_trip(self.alice)
        first = add_trip_note(
            self.alice,
            story.pk,
            comment="walk",
            published=timezone.now(),
            idempotency_key="note-key-2",
        )
        stop_trip(self.alice, story.pk)
        second = add_trip_note(
            self.alice,
            story.pk,
            comment="walk",
            published=timezone.now(),
            idempotency_key="note-key-2",
        )
        self.assertEqual(first.pk, second.pk)

    def test_add_trip_note_without_key_allows_duplicates(self):
        # No key => current at-least-once behavior is preserved.
        story = start_trip(self.alice)
        a = add_trip_note(
            self.alice, story.pk, comment="same", published=timezone.now()
        )
        b = add_trip_note(
            self.alice, story.pk, comment="same", published=timezone.now()
        )
        self.assertNotEqual(a.pk, b.pk)

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

    def test_get_detail_returns_journal_events_newest_first(self):
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
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))
        # Three notes were posted; the #poi hashtag also created a
        # HabitTracked linked to the story, but the detail view
        # intentionally omits non-journal events.
        self.assertEqual(len(events), 3)
        self.assertTrue(all(e["type"] == "journal" for e in events))

    def test_get_detail_other_user_raises(self):
        story = start_trip(self.alice)
        with self.assertRaises(StoryNotFoundError):
            get_detail(self.bob, story.pk)


class TripShareServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")
        Profile.objects.create(user=cls.alice, default_board_thread=cls.daily)
        Profile.objects.create(user=cls.bob, default_board_thread=cls.daily)

    def test_share_trip_creates_share_with_uuid(self):
        story = start_trip(self.alice)
        share = share_trip(self.alice, story.pk)
        self.assertEqual(share.story, story)
        self.assertIsNotNone(share.uuid)
        self.assertEqual(SharedStory.objects.filter(story=story).count(), 1)

    def test_share_trip_is_get_or_create(self):
        story = start_trip(self.alice)
        first = share_trip(self.alice, story.pk)
        second = share_trip(self.alice, story.pk)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.uuid, second.uuid)

    def test_share_trip_works_on_stopped_trip(self):
        story = start_trip(self.alice)
        stop_trip(self.alice, story.pk)
        share = share_trip(self.alice, story.pk)
        self.assertEqual(share.story, story)

    def test_share_trip_other_user_raises(self):
        story = start_trip(self.alice)
        with self.assertRaises(StoryNotFoundError):
            share_trip(self.bob, story.pk)

    def test_unshare_trip_deletes_share_and_is_idempotent(self):
        story = start_trip(self.alice)
        share_trip(self.alice, story.pk)
        unshare_trip(self.alice, story.pk)
        self.assertFalse(SharedStory.objects.filter(story=story).exists())
        unshare_trip(self.alice, story.pk)

    def test_unshare_trip_other_user_raises(self):
        story = start_trip(self.alice)
        share_trip(self.alice, story.pk)
        with self.assertRaises(StoryNotFoundError):
            unshare_trip(self.bob, story.pk)
        self.assertTrue(SharedStory.objects.filter(story=story).exists())

    def test_reshare_after_revoke_mints_new_uuid(self):
        story = start_trip(self.alice)
        first = share_trip(self.alice, story.pk)
        unshare_trip(self.alice, story.pk)
        second = share_trip(self.alice, story.pk)
        self.assertNotEqual(first.uuid, second.uuid)

    def test_get_shared_story_finds_share_by_uuid(self):
        story = start_trip(self.alice)
        share = share_trip(self.alice, story.pk)
        found = get_shared_story(share.uuid)
        self.assertEqual(found.pk, share.pk)
        self.assertEqual(found.story.pk, story.pk)

    def test_get_shared_story_unknown_uuid_returns_none(self):
        self.assertIsNone(get_shared_story(uuid.uuid4()))


class TripPhotoServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")
        Profile.objects.create(user=cls.alice, default_board_thread=cls.daily)
        Profile.objects.create(user=cls.bob, default_board_thread=cls.daily)

    def setUp(self):
        # Confirm reads the uploaded original's EXIF for the capture time; keep
        # that download hermetic by default (no real S3, empty bytes -> no EXIF
        # -> the provided ``published`` is used unchanged). Individual tests
        # override ``download_bytes`` to supply EXIF-bearing image bytes.
        patcher = mock.patch(f"{STORAGE}.download_bytes", return_value=b"")
        patcher.start()
        self.addCleanup(patcher.stop)

    @mock.patch(f"{STORAGE}.presign_put", return_value="https://put.example/x")
    def test_presign_allocates_key_under_user_story_prefix(self, _put):
        story = start_trip(self.alice)
        result = presign_photo_upload(self.alice, story.pk, content_type="image/jpeg")
        self.assertTrue(result["key"].startswith(f"trips/{self.alice.pk}/{story.pk}/"))
        self.assertTrue(result["key"].endswith(".jpg"))
        self.assertEqual(result["upload_url"], "https://put.example/x")
        self.assertIn("expires_at", result)

    def test_presign_rejects_unsupported_content_type(self):
        story = start_trip(self.alice)
        with self.assertRaises(ValueError):
            presign_photo_upload(self.alice, story.pk, content_type="image/gif")

    @mock.patch(f"{STORAGE}.presign_put", return_value="https://put.example/x")
    def test_presign_on_stopped_story_raises(self, _put):
        story = start_trip(self.alice)
        stop_trip(self.alice, story.pk)
        with self.assertRaises(StoryStoppedError):
            presign_photo_upload(self.alice, story.pk, content_type="image/jpeg")

    def test_presign_other_user_raises(self):
        story = start_trip(self.alice)
        with self.assertRaises(StoryNotFoundError):
            presign_photo_upload(self.bob, story.pk, content_type="image/jpeg")

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_trip_photo_creates_event_and_links(self, _exists):
        story = start_trip(self.alice)
        key = f"trips/{self.alice.pk}/{story.pk}/abc.jpg"
        photo = add_trip_photo(
            self.alice,
            story.pk,
            key=key,
            comment="sunset",
            content_type="image/jpeg",
            published=timezone.now(),
        )
        self.assertIsInstance(photo, PhotoAdded)
        self.assertEqual(photo.original_key, key)
        self.assertIsNone(photo.thumbnail_key)
        self.assertTrue(StoryEvent.objects.filter(story=story, event=photo).exists())

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_trip_photo_idempotency_returns_same_photo(self, _exists):
        # A retried confirm carrying the same key creates exactly one photo.
        story = start_trip(self.alice)
        key = f"trips/{self.alice.pk}/{story.pk}/abc.jpg"
        first = add_trip_photo(
            self.alice,
            story.pk,
            key=key,
            comment="sunset",
            content_type="image/jpeg",
            published=timezone.now(),
            idempotency_key="photo-key-1",
        )
        second = add_trip_photo(
            self.alice,
            story.pk,
            key=key,
            comment="sunset",
            content_type="image/jpeg",
            published=timezone.now(),
            idempotency_key="photo-key-1",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            PhotoAdded.objects.filter(idempotency_key="photo-key-1").count(), 1
        )
        self.assertEqual(StoryEvent.objects.filter(story=story, event=first).count(), 1)

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_trip_photo_with_poi_creates_habittracked(self, _exists):
        story = start_trip(self.alice)
        key = f"trips/{self.alice.pk}/{story.pk}/abc.jpg"
        comment = "#poi lat=40.7128 lng=-74.0060\nat the pier"
        photo = add_trip_photo(
            self.alice,
            story.pk,
            key=key,
            comment=comment,
            content_type="image/jpeg",
            published=timezone.now(),
        )
        habit = HabitTracked.objects.filter(habit__slug="poi").first()
        self.assertIsNotNone(habit)
        self.assertTrue(StoryEvent.objects.filter(story=story, event=habit).exists())
        self.assertTrue(StoryEvent.objects.filter(story=story, event=photo).exists())

    @mock.patch(f"{STORAGE}.object_exists", return_value=False)
    def test_add_trip_photo_missing_object_raises(self, _exists):
        story = start_trip(self.alice)
        key = f"trips/{self.alice.pk}/{story.pk}/abc.jpg"
        with self.assertRaises(PhotoObjectMissingError):
            add_trip_photo(
                self.alice,
                story.pk,
                key=key,
                comment="x",
                content_type="image/jpeg",
                published=timezone.now(),
            )

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_trip_photo_foreign_key_prefix_raises(self, _exists):
        story = start_trip(self.alice)
        # Key belonging to another user's prefix must be rejected before
        # the object-existence check matters.
        foreign_key = f"trips/{self.bob.pk}/{story.pk}/abc.jpg"
        with self.assertRaises(PhotoObjectMissingError):
            add_trip_photo(
                self.alice,
                story.pk,
                key=foreign_key,
                comment="x",
                content_type="image/jpeg",
                published=timezone.now(),
            )

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_trip_photo_on_stopped_story_raises(self, _exists):
        story = start_trip(self.alice)
        stop_trip(self.alice, story.pk)
        with self.assertRaises(StoryStoppedError):
            add_trip_photo(
                self.alice,
                story.pk,
                key=f"trips/{self.alice.pk}/{story.pk}/abc.jpg",
                comment="x",
                content_type="image/jpeg",
                published=timezone.now(),
            )

    @mock.patch(f"{STORAGE}.presign_get", return_value="https://get.example/thumb")
    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_get_detail_includes_photo_event(self, _exists, _get):
        story = start_trip(self.alice)
        photo = add_trip_photo(
            self.alice,
            story.pk,
            key=f"trips/{self.alice.pk}/{story.pk}/abc.jpg",
            comment="hello",
            content_type="image/jpeg",
            published=timezone.now(),
        )
        # Not ready yet (no thumbnail).
        _, events = get_detail(self.alice, story.pk)
        photo_events = [e for e in events if e["type"] == "photo"]
        self.assertEqual(len(photo_events), 1)
        self.assertFalse(photo_events[0]["ready"])
        self.assertIsNone(photo_events[0]["thumbnail_url"])

        # Once the thumbnail lands, the URL is presigned and ready is True.
        PhotoAdded.objects.filter(pk=photo.pk).update(thumbnail_key="t.webp")
        _, events = get_detail(self.alice, story.pk)
        photo_events = [e for e in events if e["type"] == "photo"]
        self.assertTrue(photo_events[0]["ready"])
        self.assertEqual(photo_events[0]["thumbnail_url"], "https://get.example/thumb")

    @mock.patch(f"{STORAGE}.presign_get", return_value="https://get.example/orig")
    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_presign_photo_original_owner_only(self, _exists, _get):
        story = start_trip(self.alice)
        photo = add_trip_photo(
            self.alice,
            story.pk,
            key=f"trips/{self.alice.pk}/{story.pk}/abc.jpg",
            comment="hi",
            content_type="image/jpeg",
            published=timezone.now(),
        )
        result = presign_photo_original(self.alice, photo.pk)
        self.assertEqual(result["url"], "https://get.example/orig")
        with self.assertRaises(StoryNotFoundError):
            presign_photo_original(self.bob, photo.pk)

    @staticmethod
    def _jpeg_with_exif_datetime(dt_str):
        """A tiny JPEG carrying ``dt_str`` as its EXIF DateTime."""
        img = Image.new("RGB", (4, 4), "red")
        exif = img.getexif()
        exif[0x0132] = dt_str  # DateTime
        buf = io.BytesIO()
        img.save(buf, "JPEG", exif=exif)
        return buf.getvalue()

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_trip_photo_uses_exif_capture_time(self, _exists):
        story = start_trip(self.alice)
        upload_time = timezone.now()
        jpeg = self._jpeg_with_exif_datetime("2021:07:15 09:30:00")
        with mock.patch(f"{STORAGE}.download_bytes", return_value=jpeg):
            photo = add_trip_photo(
                self.alice,
                story.pk,
                key=f"trips/{self.alice.pk}/{story.pk}/abc.jpg",
                comment="sunset",
                content_type="image/jpeg",
                published=upload_time,
            )
        # The EXIF capture time wins over the upload time.
        expected = datetime_cls(2021, 7, 15, 9, 30, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(photo.published, expected)

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_trip_photo_falls_back_to_published_without_exif(self, _exists):
        story = start_trip(self.alice)
        upload_time = timezone.now()
        # Default setUp patch returns b"" -> no EXIF -> provided time is kept.
        photo = add_trip_photo(
            self.alice,
            story.pk,
            key=f"trips/{self.alice.pk}/{story.pk}/abc.jpg",
            comment="no exif here",
            content_type="image/jpeg",
            published=upload_time,
        )
        self.assertEqual(photo.published, upload_time)
