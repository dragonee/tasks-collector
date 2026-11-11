"""Tokens that can only read, issuing one for a script, and asking who one
is logged in as (``api/v1/me/``)."""

import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient, APITestCase

from tasks.apps.tree.models import JournalAdded
from tasks.apps.tree.tests.factories import make_token

from .models import ApiToken

ENTRY = {
    "comment": "- [x] Went for a walk",
    "thread": "Daily",
    "published": "2026-11-11T20:00:00+00:00",
    "tags": [],
}


def client_with(token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class ReadOnlyTokenTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="alice", password="pw")

    def setUp(self):
        self.reader = client_with(make_token(self.user, "Claude", read_only=True))
        self.writer = client_with(make_token(self.user, "a script"))

    def test_it_reads(self):
        response = self.reader.get(
            reverse("daily-events"), {"date": "2026-11-11", "thread": "Daily"}
        )

        self.assertEqual(response.status_code, 200)

    def test_it_writes_nothing(self):
        refused = [
            self.reader.post("/journal/", ENTRY, format="json"),
            # A view that takes tokens only, and checks its input after.
            self.reader.post(reverse("track-habit-api"), {}, format="json"),
        ]

        for response in refused:
            with self.subTest(response.request["PATH_INFO"]):
                self.assertEqual(response.status_code, 403)
                self.assertIn("only read", response.json()["detail"])
        self.assertFalse(JournalAdded.objects.exists())

    def test_it_may_preview_an_entry(self):
        response = self.reader.post(reverse("journal-preview"), ENTRY, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(JournalAdded.objects.exists())

    def test_a_token_that_writes_writes(self):
        response = self.writer.post("/journal/", ENTRY, format="json")

        self.assertEqual(response.status_code, 201)

    def test_it_says_who_and_with_what(self):
        self.assertEqual(
            self.reader.get(reverse("api-me")).json(),
            {"username": "alice", "token": {"name": "Claude", "read_only": True}},
        )

        password = APIClient()
        password.credentials(HTTP_AUTHORIZATION="Basic YWxpY2U6cHc=")  # alice:pw
        self.assertEqual(
            password.get(reverse("api-me")).json(),
            {"username": "alice", "token": None},
        )

    def test_nobody_is_nobody(self):
        self.assertEqual(APIClient().get(reverse("api-me")).status_code, 401)


class IssueTokenTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="alice", password="pw")

    def test_the_devices_page_issues_a_token_and_shows_its_key_once(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("settings-devices"), {"name": "Claude", "read_only": "on"}
        )

        token = ApiToken.objects.get()
        key = response.context["issued"]["key"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual((token.name, token.read_only), ("Claude", True))
        self.assertEqual(ApiToken.objects.for_key(key), token)
        self.assertContains(response, key)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotContains(self.client.get(reverse("settings-devices")), key)

    def test_a_token_from_the_devices_page_writes_unless_asked_not_to(self):
        self.client.force_login(self.user)

        self.client.post(reverse("settings-devices"), {"name": "a script"})

        self.assertFalse(ApiToken.objects.get().read_only)

    def test_the_command_issues_a_read_only_token(self):
        out = io.StringIO()

        call_command(
            "issue_mobile_token", "alice", "--name", "Claude", "--read-only", stdout=out
        )

        token = ApiToken.objects.for_key(out.getvalue().strip())
        self.assertEqual((token.name, token.read_only), ("Claude", True))
