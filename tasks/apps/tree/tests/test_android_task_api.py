from datetime import date as date_cls
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..models import Board, Plan, Profile, Reflection, Thread

TODAY = date_cls(2026, 5, 21)
TODAY_ISO = TODAY.isoformat()


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

    def _add(self, text, date=TODAY_ISO):
        return self.client.post(
            reverse("android-task-add"),
            {"text": text, "date": date},
            format="json",
        )

    def _complete(self, text, done, date=TODAY_ISO):
        return self.client.post(
            reverse("android-task-complete"),
            {"text": text, "done": done, "date": date},
            format="json",
        )

    def _delete(self, text, date=TODAY_ISO):
        return self.client.post(
            reverse("android-task-delete"),
            {"text": text, "date": date},
            format="json",
        )

    def _list(self, date=TODAY_ISO):
        url = reverse("android-task-today")
        if date is None:
            return self.client.get(url)
        return self.client.get(url, {"date": date})

    def test_add_creates_board_node_and_plan_line(self):
        self._auth()
        response = self._add("buy bread")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"ok": True})

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "buy bread")
        plan = Plan.objects.get(thread=self.daily)
        self.assertEqual(plan.pub_date, TODAY)

    def test_complete_then_uncomplete_round_trip(self):
        self._auth()
        self._add("buy bread")

        response = self._complete("buy bread", True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")
        self.assertEqual(reflection.pub_date, TODAY)

        response = self._complete("buy bread", False)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reflection.refresh_from_db()
        self.assertEqual(reflection.good, "")

    def test_delete_removes_plan_line(self):
        self._auth()
        self._add("buy bread")
        response = self._delete("buy bread")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        plan = Plan.objects.get(thread=self.daily)
        self.assertEqual(plan.focus, "")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])

    def test_list_returns_done_flag_and_unchecked_first(self):
        self._auth()
        for line in ("alpha", "bravo"):
            self._add(line)
        self._complete("alpha", True)

        response = self._list()
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

    def test_date_drives_target_plan(self):
        """A request that names a different date hits that day's Plan,
        regardless of the server's clock."""
        self._auth()
        yesterday = (TODAY - timedelta(days=1)).isoformat()  # 2026-05-20
        self._add("buy bread", date=yesterday)
        self._add("walk dog", date=TODAY_ISO)

        plans = {p.pub_date.isoformat(): p.focus for p in Plan.objects.all()}
        self.assertEqual(plans[yesterday], "buy bread")
        self.assertEqual(plans[TODAY_ISO], "walk dog")

        # Listing yesterday only shows yesterday's task.
        response = self._list(date=yesterday)
        self.assertEqual(
            response.json(),
            {"items": [{"text": "buy bread", "done": False}]},
        )

    def test_missing_token_returns_401(self):
        response = self._list()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_add_missing_text_returns_400(self):
        self._auth()
        response = self.client.post(
            reverse("android-task-add"), {"date": TODAY_ISO}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_complete_missing_done_returns_400(self):
        self._auth()
        response = self.client.post(
            reverse("android-task-complete"),
            {"text": "x", "date": TODAY_ISO},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_missing_date_returns_400(self):
        self._auth()
        response = self.client.post(
            reverse("android-task-add"), {"text": "x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_missing_date_returns_400(self):
        self._auth()
        response = self._list(date=None)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_malformed_date_returns_400(self):
        self._auth()
        response = self._add("x", date="not-a-date")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self._list(date="2026/05/21")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_board_returns_409(self):
        Board.objects.all().delete()
        self._auth()
        response = self._add("x")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
