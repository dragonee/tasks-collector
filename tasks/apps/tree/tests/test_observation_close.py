"""Closing an observation records one ObservationClosed on its stream and
removes the Observation row. The closed detail and insight pages look the
close event up with get(), so a stream must never get two."""

import threading
from datetime import date

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models.signals import post_save
from django.test import TransactionTestCase

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import (
    InsightRefined,
    Observation,
    ObservationClosed,
    ObservationType,
    Thread,
)
from ..services.observations.closing import close_observation


def _observation(user, thread, type):
    return Observation.objects.create(
        user=user,
        thread=thread,
        type=type,
        pub_date=date(2026, 10, 20),
        situation="what happened",
        approach="next time",
    )


class ObservationCloseAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.thread = Thread.objects.create(name="Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.observation = _observation(self.user, self.thread, self.type)

    def test_close_records_close_event_once(self):
        url = f"/observations/{self.observation.pk}/close/"

        resp = self.client.post(url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["HX-Redirect"], "/observations/")
        self.assertFalse(Observation.objects.exists())

        closed = ObservationClosed.objects.get()
        self.assertEqual(closed.event_stream_id, self.observation.event_stream_id)
        self.assertEqual(closed.situation, "what happened")

        self.assertEqual(self.client.post(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ObservationClosed.objects.count(), 1)

    def test_close_and_extract_records_close_and_insight_once(self):
        url = f"/observations/{self.observation.pk}/close-and-extract/"
        stream_id = self.observation.event_stream_id

        resp = self.client.post(url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["HX-Redirect"], f"/insights/{stream_id}/")

        insight = InsightRefined.objects.get()
        self.assertEqual(insight.event_stream_id, stream_id)
        self.assertEqual(insight.approach, "next time")

        self.assertEqual(self.client.post(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ObservationClosed.objects.count(), 1)
        self.assertEqual(InsightRefined.objects.count(), 1)


class ConcurrentCloseTestCase(TransactionTestCase):
    """Two requests closing the same observation at once, e.g. a
    double-clicked Close button."""

    def setUp(self):
        User = get_user_model()
        user = User.objects.create_user(username="u", password="x")
        thread = Thread.objects.create(name="Daily")
        type = ObservationType.objects.create(name="Error", slug="error")
        self.observation = _observation(user, thread, type)

    def test_concurrent_closes_record_one_close_event(self):
        first_saved = threading.Event()
        release_first = threading.Event()
        results = {}

        def hold_first_before_commit(sender, instance, **kwargs):
            if threading.current_thread().name == "first":
                first_saved.set()
                release_first.wait(timeout=5)

        def close(name):
            def run():
                try:
                    results[name] = close_observation(self.observation.pk)
                except Observation.DoesNotExist as e:
                    results[name] = e
                finally:
                    connection.close()

            thread = threading.Thread(target=run, name=name)
            thread.start()
            return thread

        post_save.connect(hold_first_before_commit, sender=ObservationClosed)
        try:
            first = close("first")
            self.assertTrue(first_saved.wait(timeout=5))

            # The first close has saved its event but not committed. Give the
            # second one time to run as far as it can before letting go.
            second = close("second")
            second.join(timeout=0.5)
            release_first.set()

            first.join(timeout=5)
            second.join(timeout=5)
        finally:
            post_save.disconnect(hold_first_before_commit, sender=ObservationClosed)

        self.assertIsInstance(results["first"], ObservationClosed)
        self.assertIsInstance(results["second"], Observation.DoesNotExist)
        self.assertEqual(ObservationClosed.objects.count(), 1)
        self.assertFalse(Observation.objects.exists())
