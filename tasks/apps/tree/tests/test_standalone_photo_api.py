from datetime import datetime as datetime_cls
from datetime import timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..models import PhotoAdded, Profile, StoryEvent, Thread

PUB_AT = datetime_cls(2026, 5, 25, 14, 30, tzinfo=dt_timezone.utc).isoformat()
STORAGE = "tasks.apps.tree.services.photos.storage"


class StandalonePhotoAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.other = User.objects.create_user(username="other", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.other_token = Token.objects.create(user=cls.other)
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")
        Profile.objects.create(user=cls.user, default_board_thread=cls.daily)
        Profile.objects.create(user=cls.other, default_board_thread=cls.daily)

    def setUp(self):
        self._auth()
        patcher = mock.patch(f"{STORAGE}.download_bytes", return_value=b"")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _auth(self, token=None):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {(token or self.token).key}")

    def _presign(self, content_type="image/jpeg"):
        return self.client.post(
            reverse("android-photo-presign"),
            {"content_type": content_type},
            format="json",
        )

    def _confirm(
        self,
        key,
        comment="",
        content_type="image/jpeg",
        published=PUB_AT,
        idempotency_key=None,
    ):
        payload = {
            "key": key,
            "comment": comment,
            "content_type": content_type,
            "published": published,
        }
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        return self.client.post(
            reverse("android-photo-confirm"), payload, format="json"
        )

    # --- presign ---

    def test_presign_requires_auth(self):
        self.client.credentials()
        r = self._presign()
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    @mock.patch(f"{STORAGE}.presign_put", return_value="https://put.example/x")
    def test_presign_returns_url_and_user_key(self, _put):
        r = self._presign()
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["upload_url"], "https://put.example/x")
        self.assertTrue(r.data["key"].startswith(f"photos/{self.user.pk}/"))

    def test_presign_bad_content_type(self):
        r = self._presign(content_type="image/gif")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_presign_missing_content_type(self):
        r = self.client.post(reverse("android-photo-presign"), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # --- confirm ---

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_confirm_creates_photo_without_story(self, _exists):
        key = f"photos/{self.user.pk}/abc.jpg"
        r = self._confirm(key, comment="")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data["ok"])
        photo = PhotoAdded.objects.get(pk=r.data["photo_id"])
        self.assertEqual(photo.original_key, key)
        self.assertEqual(StoryEvent.objects.filter(event=photo).count(), 0)

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_confirm_idempotency_key_dedupes(self, _exists):
        key = f"photos/{self.user.pk}/abc.jpg"
        first = self._confirm(key, idempotency_key="ph-123")
        second = self._confirm(key, idempotency_key="ph-123")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["photo_id"], second.data["photo_id"])
        self.assertEqual(PhotoAdded.objects.filter(idempotency_key="ph-123").count(), 1)

    @mock.patch(f"{STORAGE}.object_exists", return_value=False)
    def test_confirm_missing_object_409(self, _exists):
        key = f"photos/{self.user.pk}/abc.jpg"
        r = self._confirm(key)
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_confirm_foreign_key_409(self, _exists):
        key = f"photos/{self.other.pk}/abc.jpg"
        r = self._confirm(key)
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_confirm_missing_published_400(self):
        key = f"photos/{self.user.pk}/abc.jpg"
        r = self.client.post(
            reverse("android-photo-confirm"),
            {"key": key, "content_type": "image/jpeg", "comment": ""},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    # --- original ---

    @mock.patch(f"{STORAGE}.presign_get", return_value="https://get.example/orig")
    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_original_returns_presigned_url(self, _exists, _get):
        key = f"photos/{self.user.pk}/abc.jpg"
        photo_id = self._confirm(key).data["photo_id"]
        r = self.client.get(reverse("android-photo-original", args=[photo_id]))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data["url"], "https://get.example/orig")

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_original_other_user_404(self, _exists):
        key = f"photos/{self.user.pk}/abc.jpg"
        photo_id = self._confirm(key).data["photo_id"]
        self._auth(self.other_token)
        r = self.client.get(reverse("android-photo-original", args=[photo_id]))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
