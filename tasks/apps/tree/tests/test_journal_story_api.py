from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import HabitTracked, JournalAdded, Story, StoryEvent, Thread


class JournalStoryAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.other = User.objects.create_user(username="other", password="x")
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _post(self, **extra):
        payload = {"comment": "hello", "thread": "Daily", "tags": []}
        payload.update(extra)
        return self.client.post(reverse("journaladded-list"), payload, format="json")

    def test_post_with_owned_story_links_story_event(self):
        story = Story.objects.create(user=self.user, title="t")
        resp = self._post(story=story.pk)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        journal = JournalAdded.objects.get(pk=resp.data["id"])
        self.assertEqual(
            StoryEvent.objects.filter(story=story, event=journal).count(), 1
        )

    def test_post_with_owned_story_links_extracted_habit(self):
        story = Story.objects.create(user=self.user, title="t")
        resp = self._post(comment="#poi lat=10 lng=20\nseaside", story=story.pk)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # 1 journal + 1 habit-tracked = 2 story_event rows
        self.assertEqual(StoryEvent.objects.filter(story=story).count(), 2)
        habit = HabitTracked.objects.get(habit__slug="poi")
        self.assertTrue(StoryEvent.objects.filter(story=story, event=habit).exists())

    def test_post_with_other_users_story_is_rejected(self):
        story = Story.objects.create(user=self.other, title="t")
        resp = self._post(story=story.pk)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(StoryEvent.objects.filter(story=story).exists())
        self.assertFalse(JournalAdded.objects.exists())

    def test_post_without_story_creates_no_story_event(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StoryEvent.objects.count(), 0)

    def test_active_story_endpoint_scopes_to_user_and_active(self):
        active = Story.objects.create(user=self.user, title="active")
        Story.objects.create(user=self.user, title="stopped", stopped=timezone.now())
        Story.objects.create(user=self.other, title="other-active")
        resp = self.client.get(reverse("stories-list"), {"active": "true"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [s["id"] for s in resp.data["results"]]
        self.assertEqual(ids, [active.pk])
