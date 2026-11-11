import uuid
from datetime import date as date_cls
from datetime import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import (
    Observation,
    ObservationClosed,
    ObservationMade,
    ObservationType,
)
from .factories import make_thread

OBSERVATIONS_URL = "/observation-api/"
EVENTS_URL = "/observation-events/"


def aware(*args):
    return timezone.make_aware(datetime(*args))


class ObservationAPIFilterTestCase(APITestCase):
    """observation-api/ filters by owner and pub_date. The CLI's observation
    list asks for ``ownership=mine`` by default."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.other = User.objects.create_user(username="o", password="x")
        cls.thread = make_thread(cls.user, "Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")

        cls.mine = cls._observation(cls.user, date_cls(2026, 10, 20), "mine")
        cls.theirs = cls._observation(cls.other, date_cls(2026, 10, 21), "theirs")
        cls.old = cls._observation(cls.user, date_cls(2025, 3, 1), "old")

    @classmethod
    def _observation(cls, user, pub_date, situation):
        return Observation.objects.create(
            user=user,
            thread=cls.thread,
            type=cls.type,
            pub_date=pub_date,
            situation=situation,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _situations(self, **params):
        resp = self.client.get(OBSERVATIONS_URL, params)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return [o["situation"] for o in resp.json()["results"]]

    def test_ownership_mine_returns_only_own_observations(self):
        self.assertEqual(self._situations(ownership="mine"), ["mine", "old"])

    def test_ownership_all_returns_every_observation_the_user_can_see(self):
        # Another user's observation is not visible unless they share it.
        self.assertEqual(self._situations(ownership="all"), ["mine", "old"])

    def test_filters_by_pub_date_range(self):
        self.assertEqual(
            self._situations(pub_date__gte="2026-01-01", pub_date__lte="2026-10-20"),
            ["mine"],
        )

    def test_filters_by_event_stream_id(self):
        self.assertEqual(
            self._situations(event_stream_id=str(self.mine.event_stream_id)), ["mine"]
        )

    def test_unknown_event_stream_id_returns_nothing(self):
        self.assertEqual(self._situations(event_stream_id=str(uuid.uuid4())), [])


class ObservationEventAPIFilterTestCase(APITestCase):
    """observation-events/ filters by stream, published range and whether the
    observation is still open. The CLI's observationdump builds on these."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.thread = make_thread(cls.user, "Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")

        cls.open_obs = Observation.objects.create(
            user=cls.user,
            thread=cls.thread,
            type=cls.type,
            pub_date=date_cls(2026, 10, 20),
            situation="open",
        )
        cls.open_made = cls._made(cls.open_obs.event_stream_id, aware(2026, 10, 20, 9))

        # Closed observations keep their events but lose the Observation row.
        closed_obs = Observation.objects.create(
            user=cls.user,
            thread=cls.thread,
            type=cls.type,
            pub_date=date_cls(2025, 3, 1),
            situation="closed",
        )
        cls.closed_made = cls._made(closed_obs.event_stream_id, aware(2025, 3, 1, 9))
        cls.closed_closed = ObservationClosed.objects.create(
            published=aware(2025, 3, 2, 9),
            event_stream_id=closed_obs.event_stream_id,
            thread=cls.thread,
            type=cls.type,
            situation="closed",
        )
        closed_obs.delete()

    @classmethod
    def _made(cls, event_stream_id, published):
        return ObservationMade.objects.create(
            published=published,
            event_stream_id=event_stream_id,
            thread=cls.thread,
            type=cls.type,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _ids(self, **params):
        resp = self.client.get(EVENTS_URL, params)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return {e["id"] for e in resp.json()["results"]}

    def test_open_true_returns_only_events_of_open_observations(self):
        self.assertEqual(self._ids(open="true"), {self.open_made.id})

    def test_open_false_returns_only_events_of_closed_observations(self):
        self.assertEqual(
            self._ids(open="false"), {self.closed_made.id, self.closed_closed.id}
        )

    def test_filters_by_event_stream_id(self):
        self.assertEqual(
            self._ids(event_stream_id=str(self.open_obs.event_stream_id)),
            {self.open_made.id},
        )

    def test_unknown_event_stream_id_returns_nothing(self):
        # Must stay an empty 200 (not a 400 "invalid choice") once the stream
        # id becomes a foreign key — the CLI's observationdump relies on it.
        self.assertEqual(self._ids(event_stream_id=str(uuid.uuid4())), set())

    def test_malformed_event_stream_id_is_rejected(self):
        resp = self.client.get(EVENTS_URL, {"event_stream_id": "not-a-uuid"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filters_by_published_range(self):
        self.assertEqual(
            self._ids(
                published__gte="2025-01-01 00:00:00",
                published__lte="2025-12-31 23:59:59",
            ),
            {self.closed_made.id, self.closed_closed.id},
        )
