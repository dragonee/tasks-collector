from datetime import date as date_cls

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..models import Board, Plan, Profile, Reflection, Thread


class AndroidTaskAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.daily = Thread.objects.create(name="Daily")
        Profile.objects.create(user=cls.user, default_board_thread=cls.daily)
        cls.board = Board.objects.create(thread=cls.daily, state=[])

    def setUp(self):
        self.board = Board.objects.get(pk=self.board.pk)
        self.board.state = []
        self.board.save()
        Plan.objects.filter(thread=self.daily).delete()
        Reflection.objects.filter(thread=self.daily).delete()

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_add_creates_board_node_and_plan_line(self):
        self._auth()
        response = self.client.post(
            reverse("android-task-add"), {"text": "buy bread"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"ok": True})

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "buy bread")
        self.assertTrue(Plan.objects.filter(thread=self.daily).exists())

    def test_complete_then_uncomplete_round_trip(self):
        self._auth()
        self.client.post(
            reverse("android-task-add"), {"text": "buy bread"}, format="json"
        )

        response = self.client.post(
            reverse("android-task-complete"),
            {"text": "buy bread", "done": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

        response = self.client.post(
            reverse("android-task-complete"),
            {"text": "buy bread", "done": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reflection.refresh_from_db()
        self.assertEqual(reflection.good, "")

    def test_delete_removes_plan_line(self):
        self._auth()
        self.client.post(
            reverse("android-task-add"), {"text": "buy bread"}, format="json"
        )
        response = self.client.post(
            reverse("android-task-delete"), {"text": "buy bread"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        plan = Plan.objects.get(thread=self.daily)
        self.assertEqual(plan.focus, "")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])

    def test_list_returns_done_flag_and_unchecked_first(self):
        self._auth()
        for line in ("alpha", "bravo"):
            self.client.post(reverse("android-task-add"), {"text": line}, format="json")
        self.client.post(
            reverse("android-task-complete"),
            {"text": "alpha", "done": True},
            format="json",
        )

        response = self.client.get(reverse("android-task-today"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {"text": "bravo", "done": False},
                    {"text": "alpha", "done": True},
                ]
            },
        )

    def test_missing_token_returns_401(self):
        response = self.client.get(reverse("android-task-today"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_add_missing_text_returns_400(self):
        self._auth()
        response = self.client.post(reverse("android-task-add"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_complete_missing_done_returns_400(self):
        self._auth()
        response = self.client.post(
            reverse("android-task-complete"), {"text": "x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_board_returns_409(self):
        Board.objects.all().delete()
        self._auth()
        response = self.client.post(
            reverse("android-task-add"), {"text": "x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
