from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..board_operations import create_task_item
from ..models import Board, Thread


class BoardUpdateEmptyStateGuardTestCase(APITestCase):
    """PUT /boards/<id>/ must refuse to erase a board that still has more
    than one item — an empty ``state`` from a client is almost always a
    stale/broken tree serialization, not an intentional clear (which goes
    through the commit endpoint).
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="web", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.daily = Thread.objects.create(name="Daily")

    def setUp(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _make_board(self, texts):
        return Board.objects.create(
            thread=self.daily, state=[create_task_item(t) for t in texts]
        )

    def _put_state(self, board, state):
        return self.client.put(f"/boards/{board.id}/", {"state": state}, format="json")

    def test_emptying_a_multi_item_board_is_rejected(self):
        board = self._make_board(["water plants", "call bank"])

        response = self._put_state(board, [])

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        board.refresh_from_db()
        self.assertEqual(len(board.state), 2)

    def test_emptying_a_single_item_board_is_allowed(self):
        board = self._make_board(["water plants"])

        response = self._put_state(board, [])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        board.refresh_from_db()
        self.assertEqual(board.state, [])

    def test_non_empty_update_passes_through(self):
        board = self._make_board(["water plants", "call bank"])
        new_state = [create_task_item("only task left")]

        response = self._put_state(board, new_state)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        board.refresh_from_db()
        self.assertEqual([n["text"] for n in board.state], ["only task left"])
