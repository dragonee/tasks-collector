"""Observation routes take an integer observation id or a UUID event stream id.
Malformed ids must 404 instead of reaching the ORM and raising a 500."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from ..models import Observation, ObservationClosed, ObservationType, Thread


class ObservationRouteIdTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.thread = Thread.objects.create(name="Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")

        cls.observation = Observation.objects.create(
            user=cls.user,
            thread=cls.thread,
            type=cls.type,
            pub_date=date(2026, 10, 20),
            situation="open",
        )

        closed = Observation.objects.create(
            user=cls.user,
            thread=cls.thread,
            type=cls.type,
            pub_date=date(2026, 10, 20),
            situation="closed",
        )
        cls.closed = ObservationClosed.from_observation(closed)
        cls.closed.save()
        closed.delete()

    def setUp(self):
        self.client = Client(raise_request_exception=False)
        self.client.force_login(self.user)

    def test_malformed_observation_id_returns_404(self):
        for method, url in [
            ("get", "/observations/abc/"),
            ("get", "/observations/-/"),
            ("post", "/observations/abc/close/"),
            ("post", "/observations/abc/close-and-extract/"),
            ("post", "/observations/abc/attach/"),
            ("post", "/observations/abc/detach/"),
            ("get", "/observations/abc/attachments/"),
        ]:
            with self.subTest(url=url):
                resp = getattr(self.client, method)(url)
                self.assertEqual(resp.status_code, 404)

    def test_malformed_event_stream_id_returns_404(self):
        for method, url in [
            ("get", "/observations/closed/abc/"),
            ("post", "/observations/closed/abc/extract-insight/"),
            ("get", "/insights/abc/"),
        ]:
            with self.subTest(url=url):
                resp = getattr(self.client, method)(url)
                self.assertEqual(resp.status_code, 404)

    def test_valid_ids_still_resolve(self):
        stream_id = self.closed.event_stream_id

        for url in [
            f"/observations/{self.observation.pk}/",
            f"/observations/{self.observation.pk}/attachments/",
            f"/observations/closed/{stream_id}/",
            f"/insights/{stream_id}/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_search_ignores_malformed_observation_param(self):
        resp = self.client.get(
            "/observations/search/", {"q": "open", "observation": "abc"}
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            [o["id"] for o in resp.json()["results"]], [self.observation.pk]
        )
