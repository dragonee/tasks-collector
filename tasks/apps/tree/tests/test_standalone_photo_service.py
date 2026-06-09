import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from PIL import Image

from ..models import HabitTracked, JournalAdded, PhotoAdded, Profile, StoryEvent, Thread
from ..services.photos import (
    PhotoObjectMissingError,
    add_standalone_photo,
    photo_key,
    photo_key_belongs_to,
    presign_standalone_photo,
)
from ..services.trips import StoryNotFoundError, presign_photo_original

STORAGE = "tasks.apps.tree.services.photos.storage"


class PhotoKeyTestCase(TestCase):
    def test_photo_key_lives_under_user_prefix(self):
        key = photo_key(7, "image/jpeg")
        self.assertTrue(key.startswith("photos/7/"))
        self.assertTrue(key.endswith(".jpg"))

    def test_photo_key_rejects_unsupported_content_type(self):
        with self.assertRaises(ValueError):
            photo_key(7, "image/gif")

    def test_photo_key_accepts_heic(self):
        self.assertTrue(photo_key(7, "image/heic").endswith(".heic"))
        self.assertTrue(photo_key(7, "image/heif").endswith(".heif"))

    def test_photo_key_belongs_to_accepts_own_prefix(self):
        self.assertTrue(photo_key_belongs_to("photos/7/abc.jpg", 7))

    def test_photo_key_belongs_to_rejects_other_user(self):
        self.assertFalse(photo_key_belongs_to("photos/8/abc.jpg", 7))

    def test_photo_key_belongs_to_rejects_trip_prefix(self):
        self.assertFalse(photo_key_belongs_to("trips/7/3/abc.jpg", 7))


class StandalonePhotoServiceTestCase(TestCase):
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
        # that download hermetic by default (empty bytes -> no EXIF -> the
        # provided ``published`` is used unchanged).
        patcher = mock.patch(f"{STORAGE}.download_bytes", return_value=b"")
        patcher.start()
        self.addCleanup(patcher.stop)

    # --- presign ---

    @mock.patch(f"{STORAGE}.presign_put", return_value="https://put.example/x")
    def test_presign_allocates_key_under_user_prefix(self, _put):
        result = presign_standalone_photo(self.alice, content_type="image/jpeg")
        self.assertTrue(result["key"].startswith(f"photos/{self.alice.pk}/"))
        self.assertTrue(result["key"].endswith(".jpg"))
        self.assertEqual(result["upload_url"], "https://put.example/x")
        self.assertIn("expires_at", result)

    def test_presign_rejects_unsupported_content_type(self):
        with self.assertRaises(ValueError):
            presign_standalone_photo(self.alice, content_type="image/gif")

    # --- confirm ---

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_standalone_photo_creates_event_without_story_link(self, _exists):
        key = f"photos/{self.alice.pk}/abc.jpg"
        photo = add_standalone_photo(
            self.alice,
            key=key,
            comment="sunset",
            content_type="image/jpeg",
            published=timezone.now(),
        )
        self.assertIsInstance(photo, PhotoAdded)
        self.assertEqual(photo.original_key, key)
        self.assertIsNone(photo.thumbnail_key)
        self.assertEqual(photo.thread, self.daily)
        # The defining property of a standalone photo: no StoryEvent link.
        self.assertEqual(StoryEvent.objects.filter(event=photo).count(), 0)

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
    def test_add_standalone_photo_ignores_exif_capture_time(self, _exists):
        # Unlike a trip photo, a standalone photo keeps the added-at time even
        # when the original carries an EXIF capture time.
        added_at = timezone.now()
        jpeg = self._jpeg_with_exif_datetime("2021:07:15 09:30:00")
        with mock.patch(f"{STORAGE}.download_bytes", return_value=jpeg):
            photo = add_standalone_photo(
                self.alice,
                key=f"photos/{self.alice.pk}/abc.jpg",
                comment="sunset",
                content_type="image/jpeg",
                published=added_at,
            )
        self.assertEqual(photo.published, added_at)

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_standalone_photo_idempotency_returns_same_photo(self, _exists):
        key = f"photos/{self.alice.pk}/abc.jpg"
        first = add_standalone_photo(
            self.alice,
            key=key,
            comment="sunset",
            content_type="image/jpeg",
            published=timezone.now(),
            idempotency_key="ph-1",
        )
        second = add_standalone_photo(
            self.alice,
            key=key,
            comment="sunset",
            content_type="image/jpeg",
            published=timezone.now(),
            idempotency_key="ph-1",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PhotoAdded.objects.filter(idempotency_key="ph-1").count(), 1)

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_standalone_photo_with_poi_creates_unlinked_habittracked(self, _exists):
        comment = "#poi lat=40.7128 lng=-74.0060\nat the pier"
        photo = add_standalone_photo(
            self.alice,
            key=f"photos/{self.alice.pk}/abc.jpg",
            comment=comment,
            content_type="image/jpeg",
            published=timezone.now(),
        )
        habit = HabitTracked.objects.filter(habit__slug="poi").first()
        self.assertIsNotNone(habit)
        # Neither the photo nor its extracted habit is linked to any story.
        self.assertEqual(StoryEvent.objects.filter(event=photo).count(), 0)
        self.assertEqual(StoryEvent.objects.filter(event=habit).count(), 0)

    @mock.patch(f"{STORAGE}.object_exists", return_value=False)
    def test_add_standalone_photo_missing_object_raises(self, _exists):
        with self.assertRaises(PhotoObjectMissingError):
            add_standalone_photo(
                self.alice,
                key=f"photos/{self.alice.pk}/abc.jpg",
                comment="x",
                content_type="image/jpeg",
                published=timezone.now(),
            )

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_standalone_photo_foreign_key_prefix_raises(self, _exists):
        with self.assertRaises(PhotoObjectMissingError):
            add_standalone_photo(
                self.alice,
                key=f"photos/{self.bob.pk}/abc.jpg",
                comment="x",
                content_type="image/jpeg",
                published=timezone.now(),
            )

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_add_standalone_photo_trip_key_prefix_raises(self, _exists):
        # A trips/ key must not be confirmable through the storyless path.
        with self.assertRaises(PhotoObjectMissingError):
            add_standalone_photo(
                self.alice,
                key=f"trips/{self.alice.pk}/9/abc.jpg",
                comment="x",
                content_type="image/jpeg",
                published=timezone.now(),
            )

    # --- generalized original (ownership by key prefix) ---

    @mock.patch(f"{STORAGE}.presign_get", return_value="https://get.example/orig")
    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_presign_original_resolves_standalone_photo_for_owner(self, _exists, _get):
        photo = add_standalone_photo(
            self.alice,
            key=f"photos/{self.alice.pk}/abc.jpg",
            comment="",
            content_type="image/jpeg",
            published=timezone.now(),
        )
        result = presign_photo_original(self.alice, photo.pk)
        self.assertEqual(result["url"], "https://get.example/orig")

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_presign_original_rejects_standalone_photo_for_other_user(self, _exists):
        photo = add_standalone_photo(
            self.alice,
            key=f"photos/{self.alice.pk}/abc.jpg",
            comment="",
            content_type="image/jpeg",
            published=timezone.now(),
        )
        with self.assertRaises(StoryNotFoundError):
            presign_photo_original(self.bob, photo.pk)

    def test_presign_original_404_for_non_photo_event(self):
        journal = JournalAdded.objects.create(
            thread=self.daily, comment="not a photo", published=timezone.now()
        )
        with self.assertRaises(StoryNotFoundError):
            presign_photo_original(self.alice, journal.pk)
