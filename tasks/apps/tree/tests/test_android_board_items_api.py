from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..board_operations import create_unscheduled_task
from ..models import Board
from ..services.boards import items
from .factories import make_board, make_profile, make_thread


class AndroidBoardItemsAPITestCase(APITestCase):
    """The board picker of the Android app: the user's current board as a
    flat list."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.daily = make_thread(cls.user, "Daily")
        make_profile(user=cls.user, default_board_thread=cls.daily)
        cls.board = make_board(thread=cls.daily, state=[])

    def setUp(self):
        self.board = Board.objects.get(pk=self.board.pk)
        self.board.state = []
        self.board.save()

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _board_items(self):
        return self.client.get(reverse("android-board-items"))

    @staticmethod
    def _node(text, moscow=None, state="open", children=None):
        """Build a Board.state node mirroring create_unscheduled_task's shape, with
        an optional MoSCoW marker, work state, and children.
        """
        node = create_unscheduled_task(text)
        items.set_checked(node, state == "done")
        node["data"]["meaningfulMarkers"]["moscow"] = moscow
        node["children"] = children or []
        return node

    def test_board_items_flatten_order_and_depth(self):
        # root -> child -> grandchild, plus a second root sibling.
        self.board.state = [
            self._node(
                "root",
                children=[
                    self._node("child", children=[self._node("grandchild")]),
                ],
            ),
            self._node("root2"),
        ]
        self.board.save()
        self._auth()

        response = self._board_items()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.json()["items"]
        self.assertEqual(
            [(it["text"], it["depth"]) for it in items],
            [("root", 0), ("child", 1), ("grandchild", 2), ("root2", 0)],
        )

    def test_board_items_moscow_passthrough(self):
        self.board.state = [
            self._node("must task", moscow="must"),
            self._node("wont task", moscow="wont"),
            self._node("unclassified task", moscow=None),
        ]
        self.board.save()
        self._auth()

        items = self._board_items().json()["items"]
        by_text = {it["text"]: it["moscow"] for it in items}
        self.assertEqual(by_text["must task"], "must")
        # Explicitly guard the "wont" bucket id against a "would" typo.
        self.assertEqual(by_text["wont task"], "wont")
        self.assertIsNone(by_text["unclassified task"])

    def test_board_items_done_flag(self):
        self.board.state = [
            self._node("finished", state="done"),
            self._node("open one", state="open"),
        ]
        self.board.save()
        self._auth()

        items = self._board_items().json()["items"]
        by_text = {it["text"]: it["done"] for it in items}
        self.assertTrue(by_text["finished"])
        self.assertFalse(by_text["open one"])

    def test_board_items_empty_board(self):
        self.board.state = []
        self.board.save()
        self._auth()

        response = self._board_items()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"items": []})

    def test_board_items_no_board_returns_409(self):
        Board.objects.all().delete()
        self._auth()
        response = self._board_items()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_board_items_missing_token_returns_401(self):
        response = self._board_items()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
