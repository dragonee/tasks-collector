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


class JournalEntryTagTestCase(APITestCase):
    """An entry's "+Tag" form tags it with one of the user's tags, by name,
    making the tag when it is new: how a user without tags gets one."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        cls.alices_garden = JournalTag.objects.create(
            user=cls.alice, name="ALICES-GARDEN", slug="garden"
        )
        cls.alices_entry = JournalAdded.objects.create(
            thread=Thread.objects.daily(cls.alice), comment="hers"
        )

    def setUp(self):
        self.client.force_login(self.bob)
        self.entry = JournalAdded.objects.create(
            thread=Thread.objects.daily(self.bob), comment="BOBS-ENTRY"
        )

    def _tag(self, name, entry=None, htmx=True):
        entry = entry or self.entry
        headers = {"HTTP_HX_REQUEST": "true"} if htmx else {}
        return self.client.post(
            f"/diary/entries/{entry.pk}/tags/", {"name": name}, **headers
        )

    def test_a_new_name_makes_the_users_tag_and_tags_the_entry(self):
        response = self._tag("Garden walks")

        self.assertContains(response, "Tagged Garden walks")
        tag = JournalTag.objects.get(user=self.bob)
        self.assertEqual((tag.name, tag.slug), ("Garden walks", "garden-walks"))
        self.assertEqual(list(self.entry.tags.all()), [tag])

    def test_a_known_name_or_slug_reuses_the_users_tag(self):
        mine = JournalTag.objects.create(
            user=self.bob, name="Thoughts & ideas", slug="thoughts"
        )
        other = JournalAdded.objects.create(
            thread=Thread.objects.daily(self.bob), comment="another"
        )

        self._tag("thoughts & IDEAS")
        self._tag("Thoughts", entry=other)

        self.assertEqual(JournalTag.objects.filter(user=self.bob).count(), 1)
        self.assertEqual(list(self.entry.tags.all()), [mine])
        self.assertEqual(list(other.tags.all()), [mine])

    def test_tagging_adds_to_the_entrys_tags(self):
        self._tag("first")
        self._tag("second")

        self.assertEqual(
            sorted(self.entry.tags.values_list("slug", flat=True)), ["first", "second"]
        )

    def test_someone_elses_tag_name_makes_a_tag_of_ones_own(self):
        self._tag("garden")

        self.assertEqual(
            list(self.entry.tags.all()), [JournalTag.objects.get(user=self.bob)]
        )
        self.assertEqual(list(self.alices_garden.journals.all()), [])

    def test_someone_elses_entry_is_not_found(self):
        response = self._tag("mine now", entry=self.alices_entry)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(JournalTag.objects.filter(user=self.bob).exists())
        self.assertFalse(self.alices_entry.tags.exists())

    def test_a_name_without_letters_or_a_reserved_one_is_refused(self):
        for name in ("", "  ", "!!!", "Add"):
            with self.subTest(name=name):
                response = self._tag(name)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "errorlist")
        self.assertFalse(JournalTag.objects.filter(user=self.bob).exists())

    def test_without_htmx_it_goes_back_to_the_diary(self):
        response = self._tag("plain", htmx=False)

        self.assertRedirects(response, "/diary/", fetch_redirect_response=False)
        self.assertEqual(self.entry.tags.get().slug, "plain")

    def test_the_diary_offers_the_form_and_the_users_tag_names(self):
        JournalTag.objects.create(user=self.bob, name="BOBS-TAG", slug="bobs")

        response = self.client.get("/diary/")

        self.assertContains(response, "+Tag")
        self.assertContains(response, f'hx-post="/diary/entries/{self.entry.pk}/tags/"')
        self.assertContains(response, '<option value="BOBS-TAG">')
        self.assertNotContains(response, "ALICES-GARDEN")
