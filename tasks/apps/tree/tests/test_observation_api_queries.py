"""observation-api/ and observations/search/ serialize each observation's
user, thread and type (and with ?features=updates, its updates). The query
count must not grow with the number of observations on the page."""

from datetime import date

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Observation, ObservationType, ObservationUpdated, Thread


class ObservationAPIQueryCountTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.thread = Thread.objects.create(name="Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _observation(self, situation):
        observation = Observation.objects.create(
            user=self.user,
            thread=self.thread,
            type=self.type,
            pub_date=date(2026, 10, 20),
            situation=situation,
        )
        ObservationUpdated.objects.create(observation=observation, comment="first")
        ObservationUpdated.objects.create(observation=observation, comment="second")
        return observation

    def _count_queries(self, url, params, expected_results):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url, params)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["results"]), expected_results)
        return len(ctx.captured_queries)

    def _assert_constant_queries(self, url, params):
        self._observation("deadline")
        one = self._count_queries(url, params, 1)

        for _ in range(4):
            self._observation("deadline")
        five = self._count_queries(url, params, 5)

        self.assertEqual(five, one)

    def test_list_query_count_is_constant(self):
        self._assert_constant_queries("/observation-api/", {})

    def test_list_with_updates_query_count_is_constant(self):
        self._assert_constant_queries("/observation-api/", {"features": "updates"})

    def test_text_search_query_count_is_constant(self):
        self._assert_constant_queries("/observations/search/", {"q": "deadline"})

    def test_list_with_updates_returns_updates_in_order(self):
        observation = self._observation("deadline")

        resp = self.client.get("/observation-api/", {"features": "updates"})

        [result] = resp.json()["results"]
        self.assertEqual(result["id"], observation.pk)
        self.assertEqual([u["comment"] for u in result["updates"]], ["first", "second"])

    def test_id_search_matches_id_prefix(self):
        observations = [self._observation(str(i)) for i in range(12)]
        target = observations[-1]

        resp = self.client.get("/observations/search/", {"q": f"#{target.pk}"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in resp.json()["results"]]
        self.assertIn(target.pk, ids)
        self.assertTrue(all(str(i).startswith(str(target.pk)) for i in ids))
