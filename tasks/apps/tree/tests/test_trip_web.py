"""Read-only web (HTML) views for Trips: index, detail, and the photo
miniature + trip badge rendered through the shared journal partial."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import JournalAdded, PhotoAdded, Profile, Story, StoryEvent, Thread
from ..views_trip import attach_photo_urls

STORAGE = "tasks.apps.tree.services.photos.storage"


class TripWebTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="me", password="x")
        cls.other = User.objects.create_user(username="other", password="x")
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")
        Profile.objects.create(user=cls.user, default_board_thread=cls.daily)

    def setUp(self):
        self.client.force_login(self.user)
        self.story = Story.objects.create(user=self.user, title="Lisbon weekend")

    def _note(self, comment, story=None, published=None):
        note = JournalAdded.objects.create(
            thread=self.daily, comment=comment, published=published or timezone.now()
        )
        StoryEvent.objects.create(story=story or self.story, event=note)
        return note

    def _photo(self, comment="", story=None, thumbnail_key="trips/1/1/x_thumb.webp"):
        photo = PhotoAdded.objects.create(
            thread=self.daily,
            comment=comment,
            published=timezone.now(),
            original_key="trips/1/1/x.jpg",
            content_type="image/jpeg",
            thumbnail_key=thumbnail_key,
        )
        StoryEvent.objects.create(story=story or self.story, event=photo)
        return photo

    # --- trip index ---

    def test_trip_list_requires_login(self):
        self.client.logout()
        r = self.client.get(reverse("trip-list"))
        self.assertEqual(r.status_code, 302)

    def test_trip_list_shows_own_trips_with_month_archive(self):
        stopped = Story.objects.create(
            user=self.user, title="Past trip", stopped=timezone.now()
        )
        Story.objects.create(user=self.other, title="Not mine")

        r = self.client.get(reverse("trip-list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Lisbon weekend")
        self.assertContains(r, "Past trip")
        self.assertNotContains(r, "Not mine")
        self.assertContains(r, reverse("trip-detail", args=[stopped.pk]))
        # Rendered as clickable tiles.
        self.assertContains(r, "trip-tile")
        # Month archive sidebar + anchored month group.
        self.assertContains(r, 'aside class="months"')
        now = timezone.now()
        self.assertContains(r, f'href="#{now:%Y-%m}"')
        self.assertContains(r, f'id="{now:%Y-%m}"')
        # The active trip is flagged.
        self.assertContains(r, "trip-active")

    @mock.patch(f"{STORAGE}.presign_get_web")
    def test_trip_list_tile_shows_cover_photo(self, presign_get_web):
        presign_get_web.side_effect = lambda key: f"https://signed/{key}"
        self._photo()  # latest photo linked to self.story -> tile cover

        r = self.client.get(reverse("trip-list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "trip-tile-photo")
        self.assertContains(r, "https://signed/trips/1/1/x_thumb.webp")

    def test_trip_list_tile_placeholder_without_photo(self):
        r = self.client.get(reverse("trip-list"))
        # The setUp trip has no photo -> placeholder, no <img>.
        self.assertContains(r, "trip-tile-noimg")

    def test_trip_date_label_collapses_single_day(self):
        from ..views_trip import _trip_date_label

        base = timezone.now().replace(
            year=2026, month=6, day=6, hour=8, minute=0, second=0, microsecond=0
        )
        same_day = Story(started=base, stopped=base.replace(hour=20))
        active = Story(started=base, stopped=None)
        multi_day = Story(started=base, stopped=base.replace(day=8))

        # A single calendar day (or an active trip) is shown once, not as a range.
        self.assertNotIn("–", _trip_date_label(same_day))
        self.assertNotIn("–", _trip_date_label(active))
        # A real span is shown as start – end.
        self.assertIn("–", _trip_date_label(multi_day))

    # --- trip detail ---

    def test_trip_detail_404_for_other_users_story(self):
        mine = Story.objects.create(user=self.other, title="Theirs")
        r = self.client.get(reverse("trip-detail", args=[mine.pk]))
        self.assertEqual(r.status_code, 404)

    def test_trip_detail_404_for_missing(self):
        r = self.client.get(reverse("trip-detail", args=[999999]))
        self.assertEqual(r.status_code, 404)

    def test_trip_detail_renders_notes(self):
        self._note("Walked along the river")
        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Walked along the river")
        # The trip badge is suppressed on the trip's own page.
        self.assertNotContains(r, "trip-badge")
        # The month archive lives on /trips/, not the single trip page.
        self.assertNotContains(r, 'aside class="months"')
        # A single-day trip hides the day-jump nav.
        self.assertNotContains(r, 'aside class="days"')

    def test_trip_detail_multi_day_shows_day_nav(self):
        self._note("Day one", published=timezone.now() - timedelta(days=2))
        self._note("Day three", published=timezone.now())

        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'aside class="days"')

    @mock.patch(f"{STORAGE}.presign_get_web")
    def test_trip_detail_renders_photo_thumbnail(self, presign_get_web):
        presign_get_web.side_effect = lambda key: f"https://signed/{key}"
        self._photo(comment="At the beach")

        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "journal-photo")
        self.assertContains(r, "https://signed/trips/1/1/x_thumb.webp")
        # The full original is the link target.
        self.assertContains(r, "https://signed/trips/1/1/x.jpg")

    # --- attach_photo_urls helper ---

    @mock.patch(f"{STORAGE}.presign_get_web")
    def test_attach_photo_urls_sets_thumbnail_and_original(self, presign_get_web):
        presign_get_web.side_effect = lambda key: f"https://signed/{key}"
        photo = self._photo()
        note = self._note("plain")

        attach_photo_urls([photo, note])

        self.assertEqual(photo.thumbnail_url, "https://signed/trips/1/1/x_thumb.webp")
        self.assertEqual(photo.original_url, "https://signed/trips/1/1/x.jpg")
        # Plain notes are untouched.
        self.assertFalse(hasattr(note, "thumbnail_url"))

    @mock.patch(f"{STORAGE}.presign_get_web")
    def test_attach_photo_urls_thumbnail_none_when_not_ready(self, presign_get_web):
        presign_get_web.side_effect = lambda key: f"https://signed/{key}"
        photo = self._photo(thumbnail_key=None)

        attach_photo_urls([photo])

        self.assertIsNone(photo.thumbnail_url)
        self.assertEqual(photo.original_url, "https://signed/trips/1/1/x.jpg")

    # --- map provider profile setting ---

    def test_account_settings_shows_map_provider(self):
        r = self.client.get(reverse("account-settings"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="map_provider"')
        self.assertContains(r, "OpenStreetMap")
        self.assertContains(r, "Google Maps")

    def test_account_settings_saves_map_provider(self):
        r = self.client.post(
            reverse("account-settings"),
            {"map_provider": "google", "first_name": "", "last_name": ""},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Profile.objects.get(user=self.user).map_provider, "google")

    def test_body_defaults_to_osm(self):
        r = self.client.get(reverse("trip-list"))
        self.assertContains(r, 'data-map-provider="osm"')

    def test_body_reflects_chosen_map_provider(self):
        profile = Profile.objects.get(user=self.user)
        profile.map_provider = "google"
        profile.save()

        r = self.client.get(reverse("trip-list"))
        self.assertContains(r, 'data-map-provider="google"')

    # --- diary archive: same partial, so miniature + badge must render too ---

    @mock.patch(f"{STORAGE}.presign_get_web")
    def test_diary_archive_shows_miniature_and_trip_badge(self, presign_get_web):
        presign_get_web.side_effect = lambda key: f"https://signed/{key}"
        self._photo(comment="#poi lat=10 lng=20\nDiary photo")

        r = self.client.get(reverse("public-diary-archive-current-month"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "journal-photo")
        self.assertContains(r, "https://signed/trips/1/1/x_thumb.webp")
        self.assertContains(r, "trip-badge")
        self.assertContains(r, reverse("trip-detail", args=[self.story.pk]))
