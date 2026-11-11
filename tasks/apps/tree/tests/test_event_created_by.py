"""Events record who wrote them: the user acting, or by default whoever
started the event's stream. Provenance only; it never decides access."""

from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import RestrictedError
from django.test import TestCase
from django.utils import timezone

from rest_framework.test import APITestCase

from ..models import (
    Event,
    JournalAdded,
    Observation,
    ObservationMade,
    ObservationType,
    ObservationUpdated,
    Thread,
)
from ..services.trips import add_trip_note, start_trip

User = get_user_model()


def _observation(user):
    return Observation.objects.create(
        user=user,
        thread=Thread.objects.daily(user),
        type=ObservationType.objects.get_or_create(name="Error", slug="error")[0],
        pub_date=date(2026, 11, 10),
    )


class DefaultWriterTestCase(TestCase):
    def test_an_event_saved_without_a_writer_is_credited_to_its_streams_user(self):
        user = User.objects.create_user(username="u", password="x")

        journal = JournalAdded.objects.create(
            thread=Thread.objects.daily(user), comment="hello"
        )

        self.assertEqual(journal.created_by, user)


class RequestWriterTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")

    def test_api_writes_record_the_caller(self):
        self.client.force_authenticate(user=self.alice)

        journal = self.client.post(
            "/journal/",
            {"comment": "hello", "thread": "Daily", "tags": []},
            format="json",
        ).json()
        observation = self.client.post(
            "/observation-api/",
            {
                "pub_date": "2026-11-10",
                "thread": "Daily",
                "type": ObservationType.objects.create(name="Error", slug="error").slug,
                "situation": "it broke",
            },
            format="json",
        ).json()

        self.assertEqual(
            JournalAdded.objects.get(pk=journal["id"]).created_by, self.alice
        )
        made = ObservationMade.objects.get(
            event_stream=Observation.objects.get(pk=observation["id"]).event_stream
        )
        self.assertEqual(made.created_by, self.alice)

    def test_another_user_cannot_write_into_someone_elses_observation(self):
        alices = _observation(self.alice)
        self.client.force_authenticate(user=self.bob)

        response = self.client.post(
            "/updates/",
            {
                "observation": alices.pk,
                "comment": "seen it too",
                "published": timezone.now().isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ObservationUpdated.objects.exists())

    def test_the_writer_is_kept_apart_from_the_owner(self):
        # Only owners write for now; an editor writing into someone else's
        # stream (a later role) keeps their own name on the event.
        alices = _observation(self.alice)

        update = ObservationUpdated.objects.create(
            observation=alices, comment="seen it too", created_by=self.bob
        )

        self.assertEqual(update.created_by, self.bob)
        self.assertEqual(update.event_stream.created_by, self.alice)


class IdempotencyPerWriterTestCase(TestCase):
    def test_the_same_key_from_two_users_creates_two_events(self):
        alice = User.objects.create_user(username="alice", password="x")
        bob = User.objects.create_user(username="bob", password="x")
        now = timezone.now()

        alices = add_trip_note(
            alice, start_trip(alice).pk, "a", now, idempotency_key="k-1"
        )
        bobs = add_trip_note(bob, start_trip(bob).pk, "b", now, idempotency_key="k-1")
        retried = add_trip_note(alice, alices.trip.pk, "a", now, idempotency_key="k-1")

        self.assertNotEqual(alices, bobs)
        self.assertEqual(retried, alices)
        self.assertEqual(bobs.created_by, bob)


class DeletingAUserTestCase(TestCase):
    def test_a_user_with_events_can_be_deleted(self):
        user = User.objects.create_user(username="leaving", password="x")
        JournalAdded.objects.create(thread=Thread.objects.daily(user), comment="x")
        _observation(user)

        user.delete()

        self.assertFalse(Event.objects.filter(created_by_id=user.pk).exists())
        self.assertFalse(Thread.objects.filter(user_id=user.pk).exists())

    def test_a_user_whose_events_sit_in_someone_elses_thread_is_refused(self):
        owner = User.objects.create_user(username="owner", password="x")
        guest = User.objects.create_user(username="guest", password="x")
        # A guest's observation filed under the owner's thread, as old data is.
        observation = Observation.objects.create(
            user=guest,
            thread=Thread.objects.daily(owner),
            type=ObservationType.objects.create(name="Error", slug="error"),
            pub_date=date(2026, 11, 10),
        )
        ObservationMade.from_observation(observation).save()

        with self.assertRaises(RestrictedError), transaction.atomic():
            guest.delete()

        self.assertTrue(Event.objects.filter(created_by=guest).exists())
