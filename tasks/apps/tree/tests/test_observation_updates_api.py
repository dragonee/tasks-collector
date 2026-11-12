"""updates/ records an ObservationUpdated on an open observation's stream.
The CLI's `update` tool posts {"comment", "observation"} here."""

from datetime import date

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Observation, ObservationType, ObservationUpdated
from ..services.streams import share
from .factories import make_thread

UPDATES_URL = "/updates/"


class ObservationUpdatedAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.thread = make_thread(cls.user, "Daily")
        cls.type = ObservationType.objects.create(name="Error", slug="error")
        cls.observation = Observation.objects.create(
            user=cls.user,
            thread=cls.thread,
            type=cls.type,
            pub_date=date(2026, 10, 20),
            situation="open",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_create_on_observation_joins_its_stream(self):
        resp = self.client.post(
            UPDATES_URL,
            {"comment": "progress", "observation": self.observation.pk},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["observation"], self.observation.pk)

        update = ObservationUpdated.objects.get()
        self.assertEqual(update.event_stream_id, self.observation.event_stream_id)
        self.assertEqual(update.thread, self.thread)

    def test_create_with_the_list_filter_in_the_query_string(self):
        resp = self.client.post(
            f"{UPDATES_URL}?observation_id={self.observation.pk}",
            {"comment": "progress", "observation": self.observation.pk},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            ObservationUpdated.objects.get().observation_id, self.observation.pk
        )

    def test_the_list_filter_lists_one_observations_updates(self):
        ObservationUpdated.objects.create(
            observation=self.observation,
            thread=self.thread,
            comment="progress",
            event_stream_id=self.observation.event_stream_id,
        )

        resp = self.client.get(UPDATES_URL, {"observation_id": self.observation.pk})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        updates = resp.json()["results"]
        self.assertEqual([u["comment"] for u in updates], ["progress"])
        self.assertNotIn("observation_fields", updates[0])

    def test_create_without_observation_returns_400(self):
        for data in [{"comment": "orphan"}, {"comment": "orphan", "observation": None}]:
            with self.subTest(data=data):
                resp = self.client.post(UPDATES_URL, data, format="json")

                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("observation", resp.json())

        self.assertFalse(ObservationUpdated.objects.exists())

    def test_create_on_closed_observation_returns_400(self):
        pk = self.observation.pk
        self.observation.delete()

        resp = self.client.post(
            UPDATES_URL, {"comment": "late", "observation": pk}, format="json"
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("observation", resp.json())


class ObservationUpdatedFilterTestCase(APITestCase):
    """``updates/?observation_id=`` chooses among the observations the caller
    can see, so the browsable API lists no one else's and someone else's id
    answers like an unknown one."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.other = User.objects.create_user(username="o", password="x")
        type = ObservationType.objects.create(name="Error", slug="error")
        cls.mine = cls._observation(cls.user, type, "mine")
        cls.theirs = cls._observation(cls.other, type, "THEIRS-PRIVATE")
        cls.shared = cls._observation(cls.other, type, "theirs, shared")
        share(cls.other, cls.shared.event_stream, "u")

        for observation in (cls.mine, cls.theirs, cls.shared):
            ObservationUpdated.objects.create(
                observation=observation, comment=f"on {observation.situation}"
            )

    @classmethod
    def _observation(cls, user, type, situation):
        return Observation.objects.create(
            user=user,
            thread=make_thread(user, f"Daily {situation}"),
            type=type,
            pub_date=date(2026, 10, 20),
            situation=situation,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _comments(self, observation_id):
        resp = self.client.get(UPDATES_URL, {"observation_id": observation_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return [update["comment"] for update in resp.json()["results"]]

    def test_filters_by_an_observation_the_user_can_see(self):
        self.assertEqual(self._comments(self.mine.pk), ["on mine"])
        self.assertEqual(self._comments(self.shared.pk), ["on theirs, shared"])

    def test_someone_elses_observation_answers_like_an_unknown_one(self):
        theirs = self.client.get(UPDATES_URL, {"observation_id": self.theirs.pk})
        unknown = self.client.get(UPDATES_URL, {"observation_id": 999999})

        self.assertEqual(theirs.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unknown.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            theirs.json()["observation_id"][0].replace(str(self.theirs.pk), "?"),
            unknown.json()["observation_id"][0].replace("999999", "?"),
        )

    def test_the_browsable_api_lists_only_visible_observations(self):
        resp = self.client.get(UPDATES_URL, HTTP_ACCEPT="text/html")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("THEIRS-PRIVATE", resp.content.decode())
