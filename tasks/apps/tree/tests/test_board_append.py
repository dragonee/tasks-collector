from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..models import Board, Profile, Thread

APPEND_URL = "/boards/append/"


def _texts(board):
    """Root-level task texts on a board, in order."""
    return [node.get("text") for node in board.state]


class BoardAppendTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.daily = Thread.objects.create(name="Daily")
        cls.weekly = Thread.objects.create(name="Weekly")
        Profile.objects.create(user=cls.user, default_board_thread=cls.daily)
        cls.daily_board = Board.objects.create(thread=cls.daily, state=[])
        cls.weekly_board = Board.objects.create(thread=cls.weekly, state=[])

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
