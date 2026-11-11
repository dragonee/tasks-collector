import datetime

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from rest_framework import status
from rest_framework.test import APITestCase

from ..board_operations import (
    add_unscheduled_task,
    close_board,
    create_unscheduled_task,
)
from ..commit import merge
from ..models import Board
from ..services.boards import items
from ..services.tasks.operations import complete, task_for_item
from .factories import make_board, make_thread


class NormaliseTestCase(SimpleTestCase):
    def test_a_new_unscheduled_task_is_already_well_formed(self):
        item = create_unscheduled_task("water plants")
        before = {**item, "data": dict(item["data"]), "state": dict(item["state"])}

        items.normalise([item])

        self.assertEqual(item, before)
        self.assertIsNone(item["data"]["taskId"])

    def test_items_without_an_id_get_one_each(self):
        tree = [
            {"text": "a", "children": [{"text": "b", "children": []}]},
            {"id": "", "text": "c", "children": []},
        ]

        items.normalise(tree)

        ids = [item["id"] for item in items.walk(tree)]
        self.assertTrue(all(ids))
        self.assertEqual(len(set(ids)), 3)

    def test_an_existing_id_is_kept(self):
        tree = [{"id": "1", "text": "a", "data": {}, "children": []}]

        items.normalise(tree)

        self.assertEqual(tree[0]["id"], "1")

    def test_the_second_of_two_equal_ids_is_replaced(self):
        tree = [
            {"id": "same", "text": "a", "children": []},
            {"id": "same", "text": "b", "children": []},
        ]

        items.normalise(tree)

        self.assertEqual(tree[0]["id"], "same")
        self.assertNotEqual(tree[1]["id"], "same")

    def test_a_task_link_is_kept(self):
        tree = [{"id": "1", "text": "a", "data": {"taskId": "t-1"}, "children": []}]

        items.normalise(tree)

        self.assertEqual(tree[0]["data"]["taskId"], "t-1")

    def test_an_item_ticked_on_the_web_is_done(self):
        # The web board only sets state.checked.
        tree = [
            {
                "id": "1",
                "text": "a",
                "data": {"state": "open"},
                "state": {"checked": True, "expanded": True},
                "children": [],
            }
        ]

        items.normalise(tree)

        self.assertEqual(tree[0]["data"]["state"], "done")
        self.assertEqual(tree[0]["state"], {"checked": True, "expanded": True})

    def test_an_item_unticked_on_the_web_is_open(self):
        tree = [
            {
                "id": "1",
                "text": "a",
                "data": {"state": "done"},
                "state": {"checked": False},
                "children": [],
            }
        ]

        items.normalise(tree)

        self.assertEqual(tree[0]["data"]["state"], "open")

    def test_an_item_the_web_never_saved_gets_its_tick_from_data(self):
        tree = [{"id": "1", "text": "a", "data": {"state": "done"}, "children": []}]

        items.normalise(tree)

        self.assertEqual(tree[0]["state"], {"checked": True})


class BoardSaveTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.inbox = make_thread(cls.user, "Inbox")

    def test_saving_a_board_normalises_its_items(self):
        board = make_board(
            thread=self.inbox,
            state=[{"text": "a", "state": {"checked": True}, "children": []}],
        )

        board.refresh_from_db()
        (item,) = board.state
        self.assertTrue(item["id"])
        self.assertIsNone(item["data"]["taskId"])
        self.assertEqual(item["data"]["state"], "done")

    def test_appending_keeps_the_ids_of_the_other_items(self):
        board = make_board(thread=self.inbox, state=[create_unscheduled_task("a")])
        first_id = board.state[0]["id"]

        add_unscheduled_task(self.user, "b", "Inbox")

        board.refresh_from_db()
        self.assertEqual(board.state[0]["id"], first_id)
        self.assertNotEqual(board.state[1]["id"], first_id)


class BoardPutTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.inbox = make_thread(cls.user, "Inbox")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_a_tree_from_the_web_is_stored_normalised(self):
        board = make_board(thread=self.inbox, state=[])
        # As the web board sends it: UI state, no data.state change on tick.
        web_item = {
            "id": "abc",
            "text": "water plants",
            "data": {"text": "water plants", "state": "open", "meaningfulMarkers": {}},
            "state": {"checked": True, "selected": True},
            "children": [{"text": "buy a can", "data": {}, "children": []}],
        }

        response = self.client.put(
            f"/boards/{board.id}/", {"state": [web_item]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        (item,) = response.json()["state"]
        self.assertEqual(item["id"], "abc")
        self.assertEqual(item["data"]["state"], "done")
        self.assertIsNone(item["data"]["taskId"])
        self.assertTrue(item["children"][0]["id"])
        self.assertEqual(Board.objects.get(pk=board.pk).state, response.json()["state"])


def _linked(text, task_id, **markers):
    item = create_unscheduled_task(text)
    item["data"]["taskId"] = task_id
    item["data"]["meaningfulMarkers"].update(markers)
    return item


class CommitKeepsTaskLinksTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.inbox = make_thread(cls.user, "Inbox")
        cls.later = make_thread(cls.user, "Later")

    def _planned(self, text, **markers):
        """A board with one item, planned: (board, task)."""
        item = create_unscheduled_task(text)
        item["data"]["meaningfulMarkers"].update(markers)
        board = make_board(thread=self.inbox, state=[item])
        task = task_for_item(self.user, board, board.state[0])
        return board, task

    def test_an_item_that_stays_keeps_its_id_and_task(self):
        board, task = self._planned("a")
        item_id = board.state[0]["id"]

        board = close_board(board)

        (item,) = board.state
        self.assertEqual(item["id"], item_id)
        self.assertEqual(item["data"]["taskId"], str(task.pk))
        task.refresh_from_db()
        self.assertEqual((task.board, task.board_item_id), (board, item_id))

    def test_a_task_follows_its_item_to_another_board(self):
        board, task = self._planned("a", transition="Later")

        close_board(board)

        later = Board.objects.get(thread=self.later)
        (item,) = later.state
        self.assertEqual(item["data"]["taskId"], str(task.pk))
        task.refresh_from_db()
        self.assertEqual((task.board, task.board_item_id), (later, item["id"]))
        # Whoever has that board now has the task.
        self.assertEqual(task.event_stream_id, self.later.board_stream_id)

    def test_a_done_task_whose_item_is_committed_away_stays(self):
        board, task = self._planned("a")
        complete(task, self.user, day=datetime.date(2026, 11, 11))

        board = close_board(board)

        self.assertEqual(board.state, [])
        task.refresh_from_db()
        self.assertTrue(task.done)
        self.assertIsNone(task.board)

    def test_a_repeating_item_is_unscheduled_again_once_its_task_is_done(self):
        board, task = self._planned("water plants", canBePostponed=True)
        complete(task, self.user, day=datetime.date(2026, 11, 11))

        board = close_board(board)

        (item,) = board.state
        self.assertFalse(item["state"]["checked"])
        self.assertEqual(item["data"]["state"], "open")
        self.assertIsNone(item["data"]["taskId"])
        task.refresh_from_db()
        self.assertTrue(task.done)
        self.assertIsNone(task.board)

    def test_an_item_naming_no_task_is_unscheduled(self):
        # A board tree is JSON; what it says about tasks may be anything.
        board = make_board(
            thread=self.inbox,
            state=[
                _linked("a", "not-a-task-id"),
                _linked("b", "00000000-0000-0000-0000-000000000000"),
            ],
        )

        board = close_board(board)

        self.assertEqual([item["data"]["taskId"] for item in board.state], [None, None])


class WebSaveKeepsTaskLinksTestCase(APITestCase):
    """The web board saves the whole tree, and may hold one it loaded before
    an item was planned: which task an item has is the server's to say."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.inbox = make_thread(cls.user, "Inbox")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.board = make_board(
            thread=self.inbox,
            state=[create_unscheduled_task("a"), create_unscheduled_task("b")],
        )
        self.stale = Board.objects.get(pk=self.board.pk).state
        self.task = task_for_item(self.user, self.board, self.board.state[0])

    def _put(self, state):
        response = self.client.put(
            f"/boards/{self.board.pk}/", {"state": state}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()["state"]

    def test_a_stale_tree_does_not_unplan_the_item(self):
        a, b = self._put(self.stale)

        self.assertEqual(a["data"]["taskId"], str(self.task.pk))
        self.assertIsNone(b["data"]["taskId"])
        self.assertEqual(Board.objects.get(pk=self.board.pk).state, [a, b])

    def test_a_tree_cannot_give_an_item_a_task(self):
        tree = Board.objects.get(pk=self.board.pk).state
        tree[1]["data"]["taskId"] = str(self.task.pk)

        a, b = self._put(tree)

        self.assertEqual(a["data"]["taskId"], str(self.task.pk))
        self.assertIsNone(b["data"]["taskId"])

    def test_removing_the_item_unlinks_the_task(self):
        tree = Board.objects.get(pk=self.board.pk).state

        self._put(tree[1:])

        self.task.refresh_from_db()
        self.assertIsNone(self.task.board)
        self.assertIsNone(self.task.board_item_id)


class MergeKeepsTaskLinksTestCase(SimpleTestCase):
    def test_the_merged_item_is_planned_if_the_incoming_one_was(self):
        merged = merge([create_unscheduled_task("a")], [_linked("a", "t-1")])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["data"]["taskId"], "t-1")

    def test_the_link_of_the_item_already_there_wins(self):
        merged = merge([_linked("a", "t-1")], [_linked("a", "t-2")])

        self.assertEqual(merged[0]["data"]["taskId"], "t-1")
