"""Journal tags are per user: each user tags entries with, lists and filters
the diary by their own tags only, and two users may use the same slug."""

import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import JournalAdded, JournalTag, Thread


class JournalTagTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        cls.now = timezone.now()

        cls.alices_thoughts = JournalTag.objects.create(
            user=cls.alice, name="Alice's thoughts", slug="thoughts"
        )
        cls.alices_dreams = JournalTag.objects.create(
            user=cls.alice, name="ALICES-DREAMS", slug="dreams"
        )
        cls.bobs_thoughts = JournalTag.objects.create(
            user=cls.bob, name="Bob's thoughts", slug="thoughts"
        )

        cls.alices_entry = cls._entry(cls.alice, "ALICES-ENTRY", cls.alices_thoughts)
        cls.bobs_entry = cls._entry(cls.bob, "BOBS-ENTRY", cls.bobs_thoughts)

    @classmethod
    def _entry(cls, user, comment, tag):
        entry = JournalAdded.objects.create(
            thread=Thread.objects.daily(user), comment=comment, published=cls.now
        )
        entry.tags.add(tag)
        return entry

    def setUp(self):
        self.client.force_login(self.bob)
        self.client.force_authenticate(user=self.bob)

    def test_the_diary_by_tag_shows_the_users_own_tagged_entries(self):
        response = self.client.get("/diary/thoughts/")

        self.assertEqual(response.context["tag"], self.bobs_thoughts)
        self.assertContains(response, "BOBS-ENTRY")
        self.assertNotContains(response, "ALICES-ENTRY")

    def test_the_diary_offers_only_the_users_own_tags(self):
        diary = self.client.get("/diary/")
        add = self.client.get("/diary/add/")

        self.assertEqual(list(diary.context["tags"]), [self.bobs_thoughts])
        self.assertEqual(
            list(add.context["form"].fields["tag"].queryset), [self.bobs_thoughts]
        )
        self.assertNotContains(diary, "ALICES-DREAMS")
        self.assertNotContains(add, "ALICES-DREAMS")

    def test_someone_elses_tag_and_an_unknown_one_are_not_found(self):
        today = timezone.localdate()
        for url in (
            "/diary/dreams/",
            "/diary/no-such-tag/",
            f"/diary/dreams/{today.year}/{today.month}/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_api_tags_with_the_users_own_tag(self):
        response = self.client.post(
            "/journal/",
            {"comment": "new", "thread": "Daily", "tags": ["thoughts"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = JournalAdded.objects.get(pk=response.data["id"])
        self.assertEqual(list(entry.tags.all()), [self.bobs_thoughts])

    def test_the_api_refuses_someone_elses_tag_like_an_unknown_one(self):
        def error(slug):
            response = self.client.post(
                "/journal/",
                {"comment": "new", "thread": "Daily", "tags": [slug]},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            return response.json()["tags"][0].replace(slug, "?")

        self.assertEqual(error("dreams"), error("no-such-tag"))
        self.assertFalse(JournalAdded.objects.filter(comment="new").exists())

    def test_the_form_refuses_someone_elses_tag(self):
        response = self.client.post(
            "/diary/add/",
            {
                "comment": "new",
                "thread": Thread.objects.daily(self.bob).pk,
                "tag": self.alices_dreams.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("tag", response.context["form"].errors)
        self.assertFalse(JournalAdded.objects.filter(comment="new").exists())
