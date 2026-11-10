"""observations/<id>/journalize/ turns an observation's updates into journal
entries and drops the observation with its whole stream, including the
attach/detach records complex observations keep about it."""

from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import RestrictedError
from django.test import TestCase
from django.utils import timezone

from ..models import (
    Event,
    EventStream,
    JournalAdded,
    Observation,
    ObservationAttached,
    ObservationType,
    ObservationUpdated,
    Thread,
)
from ..presenters import ComplexPresenter


class JournalizeTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.daily(cls.user)
        cls.type = ObservationType.objects.create(name="Error", slug="error")

    def setUp(self):
        self.client.force_login(self.user)
        self.complex = self._observation("complex")
        self.observation = self._observation("journalized")
        ObservationUpdated.objects.create(
            observation=self.observation, comment="it went on", published=timezone.now()
        )
        self.client.post(
            f"/observations/{self.complex.pk}/attach/",
            {"other_observation_id": self.observation.pk},
        )

    def _observation(self, situation):
        return Observation.objects.create(
            user=self.user,
            thread=self.daily,
            type=self.type,
            pub_date=date(2026, 11, 10),
            situation=situation,
        )

    def _journalize(self):
        return self.client.post(f"/observations/{self.observation.pk}/journalize/")

    def test_updates_become_journal_entries(self):
        self._journalize()

        self.assertEqual(
            list(JournalAdded.objects.values_list("comment", flat=True)),
            ["it went on"],
        )

    def test_the_observation_and_its_stream_are_gone(self):
        stream_id = self.observation.event_stream_id

        self._journalize()

        self.assertFalse(Observation.objects.filter(pk=self.observation.pk).exists())
        self.assertFalse(EventStream.objects.filter(pk=stream_id).exists())
        self.assertFalse(Event.objects.filter(event_stream_id=stream_id).exists())

    def test_complex_observations_forget_the_attachment(self):
        self.assertEqual(
            ComplexPresenter(self.complex.event_stream_id).get_attached_stream_ids(),
            {self.observation.event_stream_id},
        )

        self._journalize()

        self.assertFalse(ObservationAttached.objects.exists())
        self.assertEqual(
            ComplexPresenter(self.complex.event_stream_id).get_attached_stream_ids(),
            set(),
        )
        response = self.client.get(f"/observations/{self.complex.pk}/")
        self.assertEqual(response.status_code, 200)

    def test_a_stream_with_events_cannot_be_deleted(self):
        with self.assertRaises(RestrictedError):
            self.complex.event_stream.events.first().event_stream.delete()
