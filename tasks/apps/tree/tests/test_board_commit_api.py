from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from rest_framework import status
from rest_framework.test import APITestCase

from ..board_operations import add_task_to_board, close_board, create_task_item
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


class CloseBoardLockTestCase(TestCase):
    """close_board() commits what is stored, not the caller's copy, and holds
    row locks on every board it rewrites, so it can't overwrite a concurrent
    append or Today tick."""

    @classmethod
    def setUpTestData(cls):
        cls.daily = Thread.objects.create(name="Daily")
        cls.sidetrack = Thread.objects.create(name="Sidetrack")

    def test_commits_a_task_saved_after_the_board_was_loaded(self):
        board = Board.objects.create(thread=self.daily, state=[_item("first")])
        stale = Board.objects.get(pk=board.pk)
        add_task_to_board("appended meanwhile", "Daily")

        close_board(stale)

        board.refresh_from_db()
        self.assertEqual(_texts(board), ["first", "appended meanwhile"])
        self.assertEqual(len(BoardCommitted.objects.get().before), 2)

    def test_locks_the_board_and_the_target_board(self):
        Board.objects.create(thread=self.sidetrack, state=[_item("old")])
        board = Board.objects.create(
            thread=self.daily,
            state=[_item("stays"), _item("moves", transition="Sidetrack")],
        )

        with CaptureQueriesContext(connection) as ctx:
            close_board(board)

        board_reads = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].startswith("SELECT") and 'FROM "tree_board"' in q["sql"]
        ]
        self.assertEqual(len(board_reads), 2)
        for sql in board_reads:
            self.assertIn("FOR UPDATE", sql)
