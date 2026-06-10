from datetime import datetime as datetime_cls
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..models import HabitTracked, JournalAdded, Profile, Story, StoryEvent, Thread

PUB_AT = datetime_cls(2026, 5, 25, 14, 30, tzinfo=dt_timezone.utc).isoformat()


class TripAPITestCase(APITestCase):
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

    def _auth(self, token=None):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {(token or self.token).key}")

    def _start(self, title=None):
        payload = {}
        if title is not None:
            payload["title"] = title
        return self.client.post(reverse("android-trip-start"), payload, format="json")

    def _stop(self, story_id):
        return self.client.post(
            reverse("android-trip-stop"), {"story_id": story_id}, format="json"
        )

    def _update(self, story_id, title):
        return self.client.post(
            reverse("android-trip-update"),
            {"story_id": story_id, "title": title},
            format="json",
        )

    def _note(self, story_id, comment, published=PUB_AT, idempotency_key=None):
        payload = {"story_id": story_id, "comment": comment, "published": published}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        return self.client.post(reverse("android-trip-note"), payload, format="json")

    def _list(self, page=1, page_size=20):
        return self.client.get(
            reverse("android-trip-list"),
            {"page": page, "page_size": page_size},
        )

    def _detail(self, story_id):
        return self.client.get(reverse("android-trip-detail", args=[story_id]))

    def test_requires_auth(self):
        self.client.credentials()  # clear
        r = self.client.post(reverse("android-trip-start"), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_start_returns_story_with_auto_title(self):
        self._auth()
        r = self._start()
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        story = r.json()["story"]
        self.assertTrue(story["title"].startswith("Trip "))
        self.assertEqual(story["type"], "trip")
        self.assertIsNone(story["stopped"])

    def test_start_accepts_user_title(self):
        self._auth()
        r = self._start(title="Lisbon")
        self.assertEqual(r.json()["story"]["title"], "Lisbon")

    def test_stop_sets_stopped(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        r = self._stop(sid)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(r.json()["story"]["stopped"])

    def test_stop_other_user_returns_404(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._auth(self.other_token)
        r = self._stop(sid)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_renames_trip(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        r = self._update(sid, "Renamed")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()["story"]["title"], "Renamed")

    def test_update_rejects_blank_title(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        r = self._update(sid, "   ")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_note_creates_journal_and_links_to_story(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        r = self._note(sid, "walking around")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        journal_id = r.json()["journal_id"]
        journal = JournalAdded.objects.get(pk=journal_id)
        self.assertEqual(journal.comment, "walking around")
        self.assertTrue(StoryEvent.objects.filter(story_id=sid, event=journal).exists())

    def test_note_with_poi_tag_creates_linked_habit_tracked(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        comment = "#poi lat=40.7128 lng=-74.0060\nat the pier"
        r = self._note(sid, comment)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        habits = HabitTracked.objects.filter(habit__slug="poi")
        self.assertEqual(habits.count(), 1)
        # Both events linked to the story.
        self.assertEqual(StoryEvent.objects.filter(story_id=sid).count(), 2)

    def test_note_on_stopped_story_returns_409(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._stop(sid)
        r = self._note(sid, "too late")
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)

    def test_note_requires_comment(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        r = self._note(sid, "")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_note_requires_full_iso_timestamp(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        r = self._note(sid, "x", published="2026-05-25")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_note_other_user_returns_404(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._auth(self.other_token)
        r = self._note(sid, "leak attempt")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_note_idempotency_key_dedupes(self):
        # A retried POST with the same idempotency_key returns the same
        # journal_id and creates exactly one event + one StoryEvent link.
        self._auth()
        sid = self._start().json()["story"]["id"]
        first = self._note(sid, "walking", idempotency_key="abc-123")
        second = self._note(sid, "walking", idempotency_key="abc-123")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.json()["journal_id"], second.json()["journal_id"])
        self.assertEqual(
            JournalAdded.objects.filter(idempotency_key="abc-123").count(), 1
        )
        self.assertEqual(StoryEvent.objects.filter(story_id=sid).count(), 1)

    def test_list_returns_active_and_history(self):
        self._auth()
        a = self._start(title="active").json()["story"]
        h1 = self._start(title="h1").json()["story"]
        self._stop(h1["id"])
        h2 = self._start(title="h2").json()["story"]
        self._stop(h2["id"])

        r = self._list(page=1, page_size=10)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertEqual([s["id"] for s in body["active"]], [a["id"]])
        self.assertEqual(body["total_history"], 2)
        self.assertEqual(
            sorted(s["id"] for s in body["history"]),
            sorted([h1["id"], h2["id"]]),
        )

    def test_list_history_pagination(self):
        self._auth()
        for i in range(3):
            sid = self._start(title=f"t{i}").json()["story"]["id"]
            self._stop(sid)
        r = self._list(page=1, page_size=2).json()
        self.assertEqual(len(r["history"]), 2)
        r = self._list(page=2, page_size=2).json()
        self.assertEqual(len(r["history"]), 1)

    def test_detail_returns_events_newest_first(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._note(sid, "first", published=PUB_AT)
        later = datetime_cls(2026, 5, 25, 16, 0, tzinfo=dt_timezone.utc).isoformat()
        self._note(sid, "later", published=later)
        r = self._detail(sid)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertEqual(body["story"]["id"], sid)
        pubs = [e["published"] for e in body["events"]]
        self.assertEqual(pubs, sorted(pubs, reverse=True))

    def test_detail_other_user_returns_404(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._auth(self.other_token)
        r = self._detail(sid)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def _share(self, story_id):
        return self.client.post(
            reverse("android-trip-share"), {"story_id": story_id}, format="json"
        )

    def _revoke_share(self, story_id):
        return self.client.post(
            reverse("android-trip-share-revoke"),
            {"story_id": story_id},
            format="json",
        )

    def test_share_returns_absolute_public_url(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        r = self._share(sid)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertTrue(body["shared"])
        self.assertTrue(
            body["share"]["url"].startswith("http://testserver/trips/shared/")
        )
        self.assertIn(body["share"]["uuid"], body["share"]["url"])

    def test_share_twice_returns_same_uuid(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        first = self._share(sid).json()["share"]["uuid"]
        second = self._share(sid).json()["share"]["uuid"]
        self.assertEqual(first, second)

    def test_share_works_on_stopped_trip(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._stop(sid)
        r = self._share(sid)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_share_other_user_returns_404(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._auth(self.other_token)
        r = self._share(sid)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_share_requires_story_id(self):
        self._auth()
        r = self.client.post(reverse("android-trip-share"), {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_requires_auth(self):
        self.client.credentials()
        r = self.client.post(
            reverse("android-trip-share"), {"story_id": 1}, format="json"
        )
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_revoke_share_is_idempotent(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._share(sid)
        r = self._revoke_share(sid)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertFalse(r.json()["shared"])
        r = self._revoke_share(sid)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_revoke_share_other_user_returns_404(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self._share(sid)
        self._auth(self.other_token)
        r = self._revoke_share(sid)
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_exposes_share_state_across_lifecycle(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        self.assertIsNone(self._detail(sid).json()["share"])

        share = self._share(sid).json()["share"]
        detail_share = self._detail(sid).json()["share"]
        self.assertEqual(detail_share, share)

        self._revoke_share(sid)
        self.assertIsNone(self._detail(sid).json()["share"])

    def test_reshare_after_revoke_mints_new_uuid(self):
        self._auth()
        sid = self._start().json()["story"]["id"]
        first = self._share(sid).json()["share"]["uuid"]
        self._revoke_share(sid)
        second = self._share(sid).json()["share"]["uuid"]
        self.assertNotEqual(first, second)
