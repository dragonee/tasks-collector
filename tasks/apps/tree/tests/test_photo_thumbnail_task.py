import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from PIL import Image

from ..models import PhotoAdded, Thread
from ..tasks import generate_photo_thumbnail

STORAGE = "tasks.apps.tree.services.photos.storage"


def _png_bytes(size=(1200, 800)):
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


class ThumbnailTaskTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")

    def _photo(self):
        return PhotoAdded.objects.create(
            thread=self.daily,
            comment="",
            original_key="trips/1/1/abc.jpg",
            content_type="image/jpeg",
            published=timezone.now(),
        )

    @mock.patch(f"{STORAGE}.upload_bytes")
    @mock.patch(f"{STORAGE}.download_bytes", return_value=_png_bytes())
    def test_generates_webp_thumbnail_and_records_key(self, _dl, up):
        photo = self._photo()
        generate_photo_thumbnail.apply(args=[photo.pk]).get()

        photo.refresh_from_db()
        self.assertEqual(photo.thumbnail_key, "trips/1/1/abc_thumb.webp")
        # Longest edge clamped to the configured max (default 480).
        self.assertLessEqual(max(photo.width, photo.height), 480)

        # Uploaded as WebP under the derived key.
        up.assert_called_once()
        called_key, called_data, called_ct = up.call_args.args
        self.assertEqual(called_key, "trips/1/1/abc_thumb.webp")
        self.assertEqual(called_ct, "image/webp")
        self.assertEqual(Image.open(io.BytesIO(called_data)).format, "WEBP")

    @mock.patch(f"{STORAGE}.upload_bytes")
    @mock.patch(f"{STORAGE}.download_bytes", return_value=_png_bytes())
    def test_idempotent_when_thumbnail_already_set(self, dl, up):
        photo = self._photo()
        PhotoAdded.objects.filter(pk=photo.pk).update(thumbnail_key="already.webp")
        generate_photo_thumbnail.apply(args=[photo.pk]).get()
        dl.assert_not_called()
        up.assert_not_called()
