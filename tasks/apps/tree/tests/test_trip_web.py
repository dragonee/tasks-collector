"""Web (HTML) views for Trips: index, detail, the photo miniature + trip
badge rendered through the shared journal partial, the share/unshare HTMX
toggle, and the public page behind a share link."""

import json
import uuid as uuid_module
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import (
    JournalAdded,
    PhotoAdded,
    Profile,
    SharedStory,
    Story,
    StoryEvent,
    Thread,
)
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

    def test_trip_detail_uses_map_layout_without_day_rail(self):
        # With located entries the trip detail page is a two-column map (left) +
        # history (right) layout — no day-jump rail even across several days.
        self._note(
            "#poi lat=38.7 lng=-9.1\nDay one",
            published=timezone.now() - timedelta(days=2),
        )
        self._note("#poi lat=38.8 lng=-9.2\nDay three", published=timezone.now())

        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Day one")
        self.assertContains(r, "Day three")
        self.assertContains(r, "trip-map-layout")
        self.assertContains(r, 'id="trip-map"')
        self.assertContains(r, 'id="trip-map-data"')
        self.assertNotContains(r, 'aside class="days"')

    def test_trip_detail_without_pois_shows_no_map(self):
        # A trip whose entries carry no coordinates renders the plain
        # full-width history — no map column and no Leaflet payload.
        self._note("Just a walk, no location recorded")

        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Just a walk, no location recorded")
        self.assertEqual(r.context["map_points"], [])
        self.assertNotContains(r, 'id="trip-map"')
        self.assertNotContains(r, "trip-map-layout")
        # Falls back to the full-width content layout.
        self.assertContains(r, "content-rail no-rail")

    def test_trip_detail_map_points_only_for_entries_with_coords(self):
        # Notes carrying a #poi/#coords line become map points (id + lat/lng);
        # notes without coordinates are left off the map.
        located = self._note("#coords lat=38.71 lng=-9.14\nMiradouro")
        self._note("Just a plain note, no location")

        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        points = r.context["map_points"]
        self.assertEqual([p["id"] for p in points], [located.pk])
        self.assertAlmostEqual(points[0]["lat"], 38.71)
        self.assertAlmostEqual(points[0]["lng"], -9.14)
        self.assertEqual(points[0]["note"], "Miradouro")
        self.assertFalse(points[0]["is_photo"])

    def test_trip_detail_same_day_shows_single_date(self):
        # A trip that starts and stops on the same (UTC) day shows one date,
        # not a start–stop range, in the topbar lower pane.
        start = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        self.story.started = start
        self.story.stopped = start.replace(hour=20)
        self.story.save()

        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "&ndash;")

    def test_trip_detail_multi_day_shows_date_range(self):
        # A trip spanning days shows a start–stop range in the lower pane.
        start = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        self.story.started = start
        self.story.stopped = start + timedelta(days=2)
        self.story.save()

        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "&ndash;")

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

    # --- share/unshare HTMX toggle ---

    def test_trip_detail_shows_share_control(self):
        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertContains(r, 'id="trip-share-control"')
        self.assertContains(r, reverse("trip-share", args=[self.story.pk]))

    def test_trip_detail_shows_share_url_when_shared(self):
        share = SharedStory.objects.create(story=self.story)
        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertContains(r, str(share.uuid))
        self.assertContains(r, reverse("trip-unshare", args=[self.story.pk]))

    def test_trip_share_creates_link_and_returns_control(self):
        r = self.client.post(reverse("trip-share", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        share = SharedStory.objects.get(story=self.story)
        self.assertContains(r, str(share.uuid))
        self.assertContains(r, "Unshare")
        self.assertContains(r, "trip-share-copy")

    def test_trip_unshare_deletes_link_and_returns_control(self):
        SharedStory.objects.create(story=self.story)
        r = self.client.post(reverse("trip-unshare", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(SharedStory.objects.filter(story=self.story).exists())
        self.assertContains(r, "Share")
        self.assertNotContains(r, "Unshare")

    def test_trip_share_requires_login(self):
        self.client.logout()
        r = self.client.post(reverse("trip-share", args=[self.story.pk]))
        self.assertEqual(r.status_code, 302)

    def test_trip_share_requires_post(self):
        r = self.client.get(reverse("trip-share", args=[self.story.pk]))
        self.assertEqual(r.status_code, 405)

    def test_trip_share_other_users_story_404(self):
        theirs = Story.objects.create(user=self.other, title="Theirs")
        r = self.client.post(reverse("trip-share", args=[theirs.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertFalse(SharedStory.objects.filter(story=theirs).exists())

    def test_trip_unshare_other_users_story_404(self):
        theirs = Story.objects.create(user=self.other, title="Theirs")
        SharedStory.objects.create(story=theirs)
        r = self.client.post(reverse("trip-unshare", args=[theirs.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(SharedStory.objects.filter(story=theirs).exists())

    # --- add to trip: affordance visibility ---

    def test_active_trip_shows_add_affordances(self):
        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["can_add"])
        # The grayed "+ add" trigger and the modal it opens.
        self.assertContains(r, "trip-add-trigger")
        self.assertContains(r, 'id="trip-add-modal"')
        self.assertContains(r, "trip-add-form")
        self.assertContains(r, "trip-add-photo-file")

    def test_stopped_trip_hides_add_affordances(self):
        self.story.stopped = timezone.now()
        self.story.save(update_fields=["stopped"])
        r = self.client.get(reverse("trip-detail", args=[self.story.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context["can_add"])
        self.assertNotContains(r, "trip-add-trigger")
        self.assertNotContains(r, 'id="trip-add-modal"')

    # --- add to trip: notes ---

    def test_add_note_creates_journal_and_returns_entries(self):
        r = self.client.post(
            reverse("trip-add-note", args=[self.story.pk]),
            {"comment": "Coffee by the river"},
        )
        self.assertEqual(r.status_code, 200)
        note = JournalAdded.objects.get(comment="Coffee by the river")
        self.assertTrue(
            StoryEvent.objects.filter(story=self.story, event=note).exists()
        )
        # Returns the timeline partial so HTMX can swap it in.
        self.assertContains(r, 'id="trip-entries"')
        self.assertContains(r, "Coffee by the river")

    def test_add_note_empty_comment_400(self):
        r = self.client.post(
            reverse("trip-add-note", args=[self.story.pk]), {"comment": "   "}
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(StoryEvent.objects.filter(story=self.story).exists())

    def test_add_note_requires_post(self):
        r = self.client.get(reverse("trip-add-note", args=[self.story.pk]))
        self.assertEqual(r.status_code, 405)

    def test_add_note_other_users_story_404(self):
        theirs = Story.objects.create(user=self.other, title="Theirs")
        r = self.client.post(
            reverse("trip-add-note", args=[theirs.pk]), {"comment": "hi"}
        )
        self.assertEqual(r.status_code, 404)
        self.assertFalse(StoryEvent.objects.filter(story=theirs).exists())

    def test_add_note_stopped_story_409(self):
        self.story.stopped = timezone.now()
        self.story.save(update_fields=["stopped"])
        r = self.client.post(
            reverse("trip-add-note", args=[self.story.pk]), {"comment": "too late"}
        )
        self.assertEqual(r.status_code, 409)
        self.assertFalse(StoryEvent.objects.filter(story=self.story).exists())

    # --- add to trip: photo presign ---

    def _presign(self, story_id, content_type="image/jpeg"):
        return self.client.post(
            reverse("trip-photo-presign", args=[story_id]),
            data=json.dumps({"content_type": content_type}),
            content_type="application/json",
        )

    @mock.patch(f"{STORAGE}.presign_put_web", return_value="https://put.web/x")
    def test_photo_presign_returns_web_url_and_key(self, _put):
        r = self._presign(self.story.pk)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["upload_url"], "https://put.web/x")
        self.assertTrue(
            body["key"].startswith(f"trips/{self.user.pk}/{self.story.pk}/")
        )

    def test_photo_presign_bad_content_type_400(self):
        r = self._presign(self.story.pk, content_type="image/gif")
        self.assertEqual(r.status_code, 400)

    def test_photo_presign_missing_content_type_400(self):
        r = self.client.post(
            reverse("trip-photo-presign", args=[self.story.pk]),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_photo_presign_other_users_story_404(self):
        theirs = Story.objects.create(user=self.other, title="Theirs")
        r = self._presign(theirs.pk)
        self.assertEqual(r.status_code, 404)

    @mock.patch(f"{STORAGE}.presign_put_web", return_value="https://put.web/x")
    def test_photo_presign_stopped_story_409(self, _put):
        self.story.stopped = timezone.now()
        self.story.save(update_fields=["stopped"])
        r = self._presign(self.story.pk)
        self.assertEqual(r.status_code, 409)

    # --- add to trip: photo confirm ---

    def _confirm(self, story_id, key, comment="", content_type="image/jpeg"):
        return self.client.post(
            reverse("trip-photo-confirm", args=[story_id]),
            data=json.dumps(
                {"key": key, "content_type": content_type, "comment": comment}
            ),
            content_type="application/json",
        )

    @mock.patch(
        f"{STORAGE}.presign_get_web", side_effect=lambda key: f"https://signed/{key}"
    )
    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_photo_confirm_creates_photo_and_returns_entries(self, _exists, _get):
        key = f"trips/{self.user.pk}/{self.story.pk}/abc.jpg"
        r = self._confirm(self.story.pk, key, comment="At the beach")
        self.assertEqual(r.status_code, 200)
        photo = PhotoAdded.objects.get(original_key=key)
        self.assertTrue(
            StoryEvent.objects.filter(story=self.story, event=photo).exists()
        )
        self.assertContains(r, 'id="trip-entries"')
        self.assertContains(r, "At the beach")

    def test_photo_confirm_missing_key_400(self):
        r = self.client.post(
            reverse("trip-photo-confirm", args=[self.story.pk]),
            data=json.dumps({"content_type": "image/jpeg", "comment": ""}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    @mock.patch(f"{STORAGE}.object_exists", return_value=True)
    def test_photo_confirm_stopped_story_409(self, _exists):
        self.story.stopped = timezone.now()
        self.story.save(update_fields=["stopped"])
        key = f"trips/{self.user.pk}/{self.story.pk}/abc.jpg"
        r = self._confirm(self.story.pk, key)
        self.assertEqual(r.status_code, 409)

    def test_photo_confirm_other_users_story_404(self):
        theirs = Story.objects.create(user=self.other, title="Theirs")
        key = f"trips/{self.other.pk}/{theirs.pk}/abc.jpg"
        r = self._confirm(theirs.pk, key)
        self.assertEqual(r.status_code, 404)

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


class SharedTripWebTestCase(TestCase):
    """The public (unauthenticated) trip page behind a share link."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="me", password="x")
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")
        Profile.objects.create(user=cls.user, default_board_thread=cls.daily)

    def setUp(self):
        # Deliberately no login: every request in this case is anonymous.
        self.story = Story.objects.create(user=self.user, title="Lisbon weekend")
        self.share = SharedStory.objects.create(story=self.story)

    def _url(self, share_uuid=None):
        return reverse("trip-shared-detail", args=[share_uuid or self.share.uuid])

    def _note(self, comment, published=None):
        note = JournalAdded.objects.create(
            thread=self.daily, comment=comment, published=published or timezone.now()
        )
        StoryEvent.objects.create(story=self.story, event=note)
        return note

    def test_public_page_renders_without_auth(self):
        self._note("Walked along the river")
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Lisbon weekend")
        self.assertContains(r, "Walked along the river")

    def test_public_page_has_no_chrome_or_edit_affordances(self):
        self._note("Walked along the river")
        r = self.client.get(self._url())
        self.assertNotContains(r, "has-sidebar")
        self.assertNotContains(r, "trip-share-control")
        self.assertNotContains(r, "trip-badge")
        self.assertNotContains(r, "add-breakthrough")
        # The owner-only add-to-trip affordances never appear on the public page.
        self.assertNotContains(r, "trip-add-trigger")
        self.assertNotContains(r, "trip-add-modal")

    def test_public_page_unknown_uuid_404(self):
        r = self.client.get(self._url(uuid_module.uuid4()))
        self.assertEqual(r.status_code, 404)

    def test_public_page_404_after_revoke(self):
        url = self._url()
        self.share.delete()
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)

    def test_public_page_renders_map_for_located_entries(self):
        self._note("#poi lat=38.7 lng=-9.1\nMiradouro")
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "trip-map-layout")
        self.assertContains(r, 'id="trip-map"')
        self.assertContains(r, 'id="trip-map-data"')

    @mock.patch(f"{STORAGE}.presign_get_web")
    def test_public_page_renders_photo_thumbnail(self, presign_get_web):
        presign_get_web.side_effect = lambda key: f"https://signed/{key}"
        photo = PhotoAdded.objects.create(
            thread=self.daily,
            comment="At the beach",
            published=timezone.now(),
            original_key="trips/1/1/x.jpg",
            content_type="image/jpeg",
            thumbnail_key="trips/1/1/x_thumb.webp",
        )
        StoryEvent.objects.create(story=self.story, event=photo)

        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "journal-photo")
        self.assertContains(r, "https://signed/trips/1/1/x_thumb.webp")
        self.assertContains(r, "https://signed/trips/1/1/x.jpg")
