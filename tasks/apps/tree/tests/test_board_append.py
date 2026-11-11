from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Profile
from .factories import make_board, make_profile, make_thread, make_token

APPEND_URL = "/boards/append/"


def _texts(board):
    """Root-level task texts on a board, in order."""
    return [node.get("text") for node in board.state]


class BoardAppendTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.token = make_token(cls.user)
        cls.daily = make_thread(cls.user, "Daily")
        cls.weekly = make_thread(cls.user, "Weekly")
        make_profile(user=cls.user, default_board_thread=cls.daily)
        cls.daily_board = make_board(thread=cls.daily, state=[])
        cls.weekly_board = make_board(thread=cls.weekly, state=[])

    def setUp(self):
        for board in (self.daily_board, self.weekly_board):
            board.refresh_from_db()
            board.state = []
            board.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _append(self, payload):
        return self.client.post(APPEND_URL, payload, format="json")

    def test_no_thread_name_defaults_to_profile_board_thread(self):
        response = self._append({"text": "buy milk"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.daily_board.refresh_from_db()
        self.assertEqual(_texts(self.daily_board), ["buy milk"])
        self.weekly_board.refresh_from_db()
        self.assertEqual(_texts(self.weekly_board), [])

    def test_default_follows_profile_default_board_thread(self):
        Profile.objects.filter(user=self.user).update(default_board_thread=self.weekly)

        response = self._append({"text": "quarterly review"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.weekly_board.refresh_from_db()
        self.assertEqual(_texts(self.weekly_board), ["quarterly review"])
        self.daily_board.refresh_from_db()
        self.assertEqual(_texts(self.daily_board), [])

    def test_explicit_thread_name_still_honored(self):
        response = self._append({"text": "plan week", "thread-name": "Weekly"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.weekly_board.refresh_from_db()
        self.assertEqual(_texts(self.weekly_board), ["plan week"])
        self.daily_board.refresh_from_db()
        self.assertEqual(_texts(self.daily_board), [])

    def test_missing_text_is_rejected(self):
        response = self._append({"thread-name": "Daily"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_board_for_thread_returns_conflict(self):
        self.daily_board.delete()

        response = self._append({"text": "orphan"})

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_board_is_locked_while_appending(self):
        with CaptureQueriesContext(connection) as ctx:
            response = self._append({"text": "buy milk"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        board_reads = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].startswith("SELECT") and 'FROM "tree_board"' in q["sql"]
        ]
        self.assertEqual(len(board_reads), 1)
        self.assertIn("FOR UPDATE", board_reads[0])
