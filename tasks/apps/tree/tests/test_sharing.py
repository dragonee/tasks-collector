"""Sharing a trip, observation or projected outcome lets another user see the
whole of it, read-only; revoking takes that back. Nothing else is shared."""

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ..models import (
    Breakthrough,
    EventStreamAccess,
    Habit,
    JournalAdded,
    Observation,
    ObservationAttached,
    ObservationDetached,
    ObservationType,
    ObservationUpdated,
    ProjectedOutcome,
    Thread,
)
from ..services.observations.closing import close_observation
from ..services.streams import SharingError, revoke, share, shared_with
from ..services.trips import add_trip_note, start_trip

User = get_user_model()

PRESIGN = mock.patch(
    "tasks.apps.tree.services.photos.storage.presign_get_web",
    side_effect=lambda key: f"https://signed/{key}",
)


class SharingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        cls.carol = User.objects.create_user(username="carol", password="x")
        cls.now = timezone.make_aware(datetime.datetime(2026, 11, 10, 12))

        cls.trip = start_trip(cls.alice, title="Alps")
        add_trip_note(cls.alice, cls.trip.pk, "summit", cls.now)
        JournalAdded.objects.create(
            thread=Thread.objects.daily(cls.alice),
            comment="private diary line",
            published=cls.now,
        )

        cls.obs_type = ObservationType.objects.create(name="Error", slug="error")
        cls.observation = Observation.objects.create(
            user=cls.alice,
            thread=Thread.objects.daily(cls.alice),
            type=cls.obs_type,
            pub_date=cls.now.date(),
            situation="the deploy broke",
        )
        ObservationUpdated.objects.create(
            observation=cls.observation, comment="rolled back", published=cls.now
        )

        cls.outcome = ProjectedOutcome.objects.create(
            breakthrough=Breakthrough.objects.create(user=cls.alice, slug="2026"),
            name="Run a marathon",
            description="",
            resolved_by=datetime.date(2026, 12, 31),
        )

    def setUp(self):
        self.client.force_login(self.bob)


class ShareServiceTestCase(SharingTestCase):
    def test_owner_shares_and_revokes(self):
        share(self.alice, self.trip.event_stream, "bob")
        share(self.alice, self.trip.event_stream, "bob")

        self.assertEqual(list(shared_with(self.trip.event_stream)), [self.bob])
        self.assertEqual(
            EventStreamAccess.objects.get(
                stream=self.trip.event_stream, user=self.bob
            ).role,
            EventStreamAccess.Role.VIEWER,
        )

        revoke(self.alice, self.trip.event_stream, "bob")

        self.assertEqual(list(shared_with(self.trip.event_stream)), [])

    def test_only_the_owner_can_share(self):
        with self.assertRaises(SharingError):
            share(self.bob, self.trip.event_stream, "carol")

    def test_a_viewer_cannot_pass_it_on(self):
        share(self.alice, self.trip.event_stream, "bob")

        with self.assertRaises(SharingError):
            share(self.bob, self.trip.event_stream, "carol")

    def test_diaries_habits_and_builtin_boards_are_not_shareable(self):
        daily = Thread.objects.daily(self.alice)
        habit = Habit.objects.filter(user=self.alice).first()

        for stream in (daily.journal_stream, daily.board_stream, habit.event_stream):
            with self.subTest(stream.type), self.assertRaises(SharingError):
                share(self.alice, stream, "bob")

    def test_the_owners_shares_dont_change_on_revoking_the_owner(self):
        share(self.alice, self.trip.event_stream, "bob")

        revoke(self.alice, self.trip.event_stream, "alice")

        self.assertEqual(list(shared_with(self.trip.event_stream)), [self.bob])
        self.assertTrue(
            EventStreamAccess.objects.filter(
                stream=self.trip.event_stream,
                user=self.alice,
                role=EventStreamAccess.Role.OWNER,
            ).exists()
        )

    def test_unknown_user_and_self_are_refused(self):
        with self.assertRaisesMessage(SharingError, "no user called"):
            share(self.alice, self.trip.event_stream, "nobody")
        with self.assertRaisesMessage(SharingError, "already own"):
            share(self.alice, self.trip.event_stream, "alice")


class SharingEndpointTestCase(SharingTestCase):
    def url(self):
        return f"/streams/{self.trip.event_stream_id}/sharing/"

    def test_owner_shares_through_htmx_and_sees_the_viewer(self):
        self.client.force_login(self.alice)

        response = self.client.post(
            self.url(),
            {"action": "share", "username": "bob", "next": "/trips/"},
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "bob")
        self.assertEqual(list(shared_with(self.trip.event_stream)), [self.bob])

    def test_errors_show_in_the_panel(self):
        self.client.force_login(self.alice)

        response = self.client.post(
            self.url(),
            {"action": "share", "username": "nobody"},
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "There is no user called")

    def test_without_htmx_it_goes_back_to_a_local_page_only(self):
        self.client.force_login(self.alice)

        local = self.client.post(
            self.url(), {"action": "share", "username": "bob", "next": "/trips/1/"}
        )
        foreign = self.client.post(
            self.url(),
            {"action": "revoke", "username": "bob", "next": "https://evil.example/"},
        )

        self.assertRedirects(local, "/trips/1/", fetch_redirect_response=False)
        self.assertRedirects(foreign, "/", fetch_redirect_response=False)

    def test_someone_else_cannot_share_it(self):
        response = self.client.post(self.url(), {"action": "share", "username": "bob"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(list(shared_with(self.trip.event_stream)), [])


@PRESIGN
class SharedTripTestCase(SharingTestCase):
    def test_a_shared_trip_is_listed_and_readable_but_not_changeable(self, presign):
        share(self.alice, self.trip.event_stream, "bob")

        listing = self.client.get("/trips/")
        page = self.client.get(f"/trips/{self.trip.pk}/")
        note = self.client.post(f"/trips/{self.trip.pk}/note/", {"comment": "me too"})

        self.assertContains(listing, "Shared with you")
        self.assertContains(listing, "Alps")
        self.assertContains(page, "summit")
        self.assertContains(page, "Shared with you by alice")
        self.assertNotContains(page, "trip-add-form")
        self.assertNotContains(page, "stream-sharing")
        self.assertEqual(note.status_code, 404)

    def test_revoking_hides_it_again(self, presign):
        share(self.alice, self.trip.event_stream, "bob")
        revoke(self.alice, self.trip.event_stream, "bob")

        self.assertEqual(self.client.get(f"/trips/{self.trip.pk}/").status_code, 404)

    def test_the_owner_sees_who_it_is_shared_with(self, presign):
        share(self.alice, self.trip.event_stream, "bob")
        self.client.force_login(self.alice)

        page = self.client.get(f"/trips/{self.trip.pk}/")

        self.assertContains(page, "stream-sharing")
        self.assertContains(page, "Stop sharing")

    def test_a_shared_trip_stays_out_of_the_viewers_own_pages(self, presign):
        share(self.alice, self.trip.event_stream, "bob")

        for url in ("/diary/", "/events/", "/", "/api/events/daily/"):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "summit")
        self.assertNotContains(
            self.client.get(f"/trips/{self.trip.pk}/"), "private diary line"
        )


class SharedObservationTestCase(SharingTestCase):
    def test_a_shared_observation_is_readable_but_not_changeable(self):
        share(self.alice, self.observation.event_stream, "bob")
        url = f"/observations/{self.observation.pk}/"

        page = self.client.get(url)
        listing = self.client.get("/observations/all/")
        mine = self.client.get("/observations/")
        edit = self.client.post(url, {"situation": "rewritten"})

        self.assertTemplateUsed(page, "tree/observation_shared.html")
        self.assertContains(page, "the deploy broke")
        self.assertContains(page, "rolled back")
        self.assertContains(listing, "shared by alice")
        self.assertNotContains(mine, "the deploy broke")
        self.assertEqual(edit.status_code, 404)
        self.observation.refresh_from_db()
        self.assertEqual(self.observation.situation, "the deploy broke")

    def test_a_shared_closed_observation_is_readable_without_owner_actions(self):
        share(self.alice, self.observation.event_stream, "bob")
        close_observation(self.observation.pk)
        url = f"/observations/closed/{self.observation.event_stream_id}/"

        page = self.client.get(url)

        self.assertContains(page, "the deploy broke")
        self.assertContains(page, "Shared with you by alice")
        self.assertNotContains(page, "Extract insight")
        self.assertEqual(self.client.post(f"{url}extract-insight/").status_code, 404)

    def attach_private_observation(self):
        """Alice attaches an observation she doesn't share herself to the
        shared one."""
        attached = Observation.objects.create(
            user=self.alice,
            thread=Thread.objects.daily(self.alice),
            type=self.obs_type,
            pub_date=self.now.date(),
            situation="the cause behind it",
        )
        ObservationUpdated.objects.create(
            observation=attached, comment="found the cause", published=self.now
        )
        ObservationAttached.objects.create(
            thread=self.observation.thread,
            event_stream_id=self.observation.event_stream_id,
            other_event_stream_id=attached.event_stream_id,
            observation=attached,
            published=self.now + datetime.timedelta(hours=1),
        )
        return attached

    def test_a_shared_complex_observation_shows_what_is_attached(self):
        attached = self.attach_private_observation()
        share(self.alice, self.observation.event_stream, "bob")

        page = self.client.get(f"/observations/{self.observation.pk}/")
        attachments = self.client.get(
            f"/observations/{self.observation.pk}/attachments/"
        )

        self.assertContains(page, "Attached (1)")
        self.assertContains(page, "the cause behind it")
        self.assertContains(page, "found the cause")
        self.assertNotContains(page, f'href="{attached.get_absolute_url()}"')
        self.assertNotContains(page, str(attached.event_stream_id))
        self.assertEqual(
            attachments.json()["attached_observation_stream_ids"],
            [str(attached.event_stream_id)],
        )
        self.assertEqual(self.client.get(attached.get_absolute_url()).status_code, 404)

    def test_a_shared_closed_complex_observation_shows_what_is_attached(self):
        attached = self.attach_private_observation()
        share(self.alice, self.observation.event_stream, "bob")
        close_observation(attached.pk)
        close_observation(self.observation.pk)

        page = self.client.get(
            f"/observations/closed/{self.observation.event_stream_id}/"
        )

        self.assertContains(page, "[closed] the cause behind it")
        self.assertContains(page, "found the cause")
        self.assertNotContains(page, str(attached.event_stream_id))

    def test_a_detached_observation_is_named_and_no_longer_shown(self):
        attached = self.attach_private_observation()
        ObservationDetached.objects.create(
            thread=self.observation.thread,
            event_stream_id=self.observation.event_stream_id,
            other_event_stream_id=attached.event_stream_id,
            published=self.now + datetime.timedelta(hours=2),
        )
        share(self.alice, self.observation.event_stream, "bob")

        page = self.client.get(f"/observations/{self.observation.pk}/")

        self.assertContains(page, "Detached observation:")
        self.assertContains(page, "the cause behind it")
        self.assertNotContains(page, "Attached (")
        self.assertNotContains(page, "found the cause")
        self.assertNotContains(page, str(attached.event_stream_id))

    def test_the_owner_keeps_the_links_to_what_is_attached(self):
        attached = self.attach_private_observation()
        self.client.force_login(self.alice)

        page = self.client.get(f"/observations/{self.observation.pk}/")

        self.assertContains(page, f'href="{attached.get_absolute_url()}"')
        self.assertContains(page, "Attached (1)")

    def test_a_shared_observation_cannot_be_attached_to_ones_own(self):
        share(self.alice, self.observation.event_stream, "bob")
        bobs = Observation.objects.create(
            user=self.bob,
            thread=Thread.objects.daily(self.bob),
            type=self.obs_type,
            pub_date=self.now.date(),
        )

        response = self.client.post(
            f"/observations/{bobs.pk}/attach/",
            {"other_observation_id": self.observation.pk},
        )

        self.assertEqual(response.status_code, 404)


class SharedOutcomeTestCase(SharingTestCase):
    def test_a_shared_outcome_is_listed_and_readable_but_not_changeable(self):
        share(self.alice, self.outcome.event_stream, "bob")

        breakthrough = self.client.get("/breakthrough/2026/")
        history = self.client.get(
            f"/projected-outcome/{self.outcome.event_stream_id}/events/"
        )
        close = self.client.post(f"/projected-outcome/{self.outcome.pk}/close/")

        self.assertContains(breakthrough, "Run a marathon")
        self.assertContains(history, "Run a marathon")
        self.assertContains(history, "Shared with you by alice")
        self.assertEqual(close.status_code, 404)
        self.assertTrue(ProjectedOutcome.objects.filter(pk=self.outcome.pk).exists())
