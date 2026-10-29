from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Board, Thread


class BoardListThreadFilterTestCase(APITestCase):
    """boards/?thread=<id> is how the board UI and the CLI load a thread's
    boards. A malformed id is a client error, not a 500."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        cls.weekly = Thread.objects.create(name="Weekly")
        cls.daily_board = Board.objects.create(thread=cls.daily, state=[])
        cls.weekly_board = Board.objects.create(thread=cls.weekly, state=[])

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _ids(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [board["id"] for board in response.json()["results"]]

    def test_filters_by_thread_id(self):
        response = self.client.get("/boards/", {"thread": self.weekly.id})

        self.assertEqual(self._ids(response), [self.weekly_board.id])

    def test_unknown_thread_id_returns_no_boards(self):
        response = self.client.get("/boards/", {"thread": 9999})

        self.assertEqual(self._ids(response), [])

    def test_non_numeric_thread_is_rejected(self):
        response = self.client.get("/boards/", {"thread": "Daily"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
