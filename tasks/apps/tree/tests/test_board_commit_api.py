from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from ..board_operations import create_task_item
from ..models import Board, BoardCommitted, Thread


def _item(text, transition=None):
    item = create_task_item(text)
    if transition:
        item["data"]["meaningfulMarkers"]["transition"] = transition
    return item


def _texts(board):
    return [node["text"] for node in board.state]


class BoardCommitAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        cls.sidetrack = Thread.objects.create(name="Sidetrack")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _commit(self, board_id):
        return self.client.post(f"/boards/{board_id}/commit/")

    def test_moves_marked_items_and_records_the_commit(self):
        board = Board.objects.create(
            thread=self.daily,
            state=[_item("stays"), _item("moves", transition="Sidetrack")],
        )

        response = self._commit(board.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        board.refresh_from_db()
        self.assertEqual(_texts(board), ["stays"])
        sidetrack_board = Board.objects.get(thread=self.sidetrack)
        self.assertEqual(_texts(sidetrack_board), ["moves"])
        committed = BoardCommitted.objects.get()
        self.assertEqual(committed.thread, self.daily)
        self.assertEqual(len(committed.before), 2)

    def test_unknown_board_returns_not_found(self):
        response = self._commit(9999)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_item_marked_for_unknown_thread_rolls_back_the_commit(self):
        state = [_item("stays"), _item("moves", transition="Nowhere")]
        board = Board.objects.create(thread=self.daily, state=state)
        date_started = board.date_started

        response = self._commit(board.id)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("Nowhere", response.json()["errors"])
        self.assertFalse(BoardCommitted.objects.exists())
        board.refresh_from_db()
        self.assertEqual(board.state, state)
        self.assertEqual(board.date_started, date_started)
