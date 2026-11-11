"""events/ lists the user's own events by month, photos included."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ..models import JournalAdded, PhotoAdded, Thread

User = get_user_model()


class EventArchiveTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="u", password="x")
        cls.other = User.objects.create_user(username="o", password="x")
        PhotoAdded.objects.create(
            thread=Thread.objects.daily(cls.user),
            comment="a view",
            original_key="photos/1/a.jpg",
            content_type="image/jpeg",
            published=timezone.now(),
        )
        JournalAdded.objects.create(
            thread=Thread.objects.daily(cls.other),
            comment="someone else's day",
            published=timezone.now(),
        )

    def setUp(self):
        self.client.force_login(self.user)

    @mock.patch(
        "tasks.apps.tree.services.photos.storage.presign_get_web",
        side_effect=lambda key: f"https://signed/{key}",
    )
    def test_a_month_with_a_photo_renders_it(self, presign):
        response = self.client.get("/events/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://signed/photos/1/a.jpg")

    @mock.patch(
        "tasks.apps.tree.services.photos.storage.presign_get_web",
        side_effect=lambda key: f"https://signed/{key}",
    )
    def test_lists_only_the_users_own_events(self, presign):
        response = self.client.get("/events/")

        self.assertNotContains(response, "someone else's day")
