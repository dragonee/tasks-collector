from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from ..board_operations import create_unscheduled_task
from ..models import Board
from .factories import make_board, make_thread, make_token


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
        cls.token = make_token(cls.user)
        cls.daily = make_thread(cls.user, "Daily")

    def setUp(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _make_board(self, texts):
        return make_board(
            thread=self.daily, state=[create_unscheduled_task(t) for t in texts]
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
        new_state = [create_unscheduled_task("only task left")]

        response = self._put_state(board, new_state)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        board.refresh_from_db()
        self.assertEqual([n["text"] for n in board.state], ["only task left"])


class BoardCreateDeleteNotAllowedTestCase(APITestCase):
    """boards/ only reads and updates existing boards. A POSTed board has no
    thread (the serializer can't set one), and a DELETE would bypass the
    erase guard above."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="web", password="x")
        cls.daily = make_thread(cls.user, "Daily")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_create_is_not_allowed(self):
        boards_before = Board.objects.count()

        response = self.client.post("/boards/", {"state": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Board.objects.count(), boards_before)

    def test_delete_is_not_allowed(self):
        board = make_board(
            thread=self.daily, state=[create_unscheduled_task("water plants")]
        )

        response = self.client.delete(f"/boards/{board.id}/")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Board.objects.filter(pk=board.pk).exists())
