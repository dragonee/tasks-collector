"""observations/<id>/attach/ and detach/ record ObservationAttached and
ObservationDetached events on the complex observation's stream. Both are
idempotent: re-attaching an attached observation or re-detaching a detached
one returns the latest matching event instead of recording another."""

import uuid
from datetime import date

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import (
    Observation,
    ObservationAttached,
    ObservationClosed,
    ObservationDetached,
    ObservationType,
    Thread,
)
from ..presenters import ComplexPresenter


class ObservationAttachDetachAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.thread = Thread.objects.create(name="Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.complex = self._observation("complex")
        self.other = self._observation("other")

    def _observation(self, situation):
        return Observation.objects.create(
            user=self.user,
            thread=self.thread,
            type=self.type,
            pub_date=date(2026, 10, 20),
            situation=situation,
        )

    def _attach(self, **data):
        return self.client.post(
            f"/observations/{self.complex.pk}/attach/", data, format="json"
        )

    def _detach(self, **data):
        return self.client.post(
            f"/observations/{self.complex.pk}/detach/", data, format="json"
        )

    def _attached(self):
        return ComplexPresenter(self.complex.event_stream_id).get_attached_stream_ids()

    def test_detach_after_reattach_detaches(self):
        # The frontend attaches by id and detaches by stream id string.
        stream_id = str(self.other.event_stream_id)

        self._attach(other_observation_id=self.other.pk)
        self._detach(other_event_stream_id=stream_id)
        self._attach(other_observation_id=self.other.pk)
        resp = self._detach(other_event_stream_id=stream_id)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._attached(), set())
        self.assertEqual(ObservationDetached.objects.count(), 2)

    def test_attach_by_stream_id_is_idempotent(self):
        stream_id = str(self.other.event_stream_id)

        first = self._attach(other_event_stream_id=stream_id)
        second = self._attach(other_event_stream_id=stream_id)

        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(ObservationAttached.objects.count(), 1)
        self.assertEqual(self._attached(), {self.other.event_stream_id})

    def test_detach_twice_is_idempotent(self):
        stream_id = str(self.other.event_stream_id)
        self._attach(other_observation_id=self.other.pk)

        first = self._detach(other_event_stream_id=stream_id)
        second = self._detach(other_event_stream_id=stream_id)

        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(ObservationDetached.objects.count(), 1)

    def test_attach_closed_observation_by_stream_id(self):
        closed = ObservationClosed.from_observation(self.other)
        closed.save()
        self.other.delete()

        resp = self._attach(other_event_stream_id=str(closed.event_stream_id))

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._attached(), {closed.event_stream_id})

    def test_attach_unknown_stream_returns_404(self):
        resp = self._attach(other_event_stream_id=str(uuid.uuid4()))

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(ObservationAttached.objects.exists())

    def test_attach_to_itself_returns_400(self):
        for data in [
            {"other_observation_id": self.complex.pk},
            {"other_event_stream_id": str(self.complex.event_stream_id)},
        ]:
            with self.subTest(data=data):
                resp = self._attach(**data)

                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(ObservationAttached.objects.exists())

    def test_malformed_ids_return_400(self):
        for resp in [
            self._attach(other_observation_id="abc"),
            self._attach(other_event_stream_id="abc"),
            self._detach(other_event_stream_id="abc"),
        ]:
            with self.subTest(resp=resp):
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("error", resp.json())

    def test_detach_never_attached_returns_404(self):
        resp = self._detach(other_event_stream_id=str(self.other.event_stream_id))

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(ObservationDetached.objects.exists())
