from datetime import date as date_cls

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Plan, Reflection, Thread
from ..utils.datetime import make_last_day_of_the_month, make_last_day_of_the_week

# A Thursday — end-of-week and end-of-month fall on distinct later dates.
TODAY = date_cls(2026, 6, 25)


class TodayPlansAPITestCase(APITestCase):
    """The single CLI-facing endpoint that returns the Daily / Weekly /
    Big-picture plans with each task flagged crossed-off, reusing the Today
    service's Plan.focus-vs-Reflection.good computation."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        cls.weekly = Thread.objects.create(name="Weekly")
        cls.bigpic = Thread.objects.create(name="Big-picture")
        cls.url = reverse("today-plans")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _get(self, date_str=TODAY.isoformat()):
        params = {"date": date_str} if date_str is not None else {}
        return self.client.get(self.url, params)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self._get().status_code, (401, 403))

    def test_daily_plan_flags_crossed_off_tasks_in_plan_order(self):
        Plan.objects.create(
            pub_date=TODAY, thread=self.daily, focus="alpha\nbravo\ncharlie"
        )
        # "bravo" appears verbatim in good -> it's crossed off.
        Reflection.objects.create(pub_date=TODAY, thread=self.daily, good="bravo")

        resp = self._get()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        daily = resp.json()["daily"]
        self.assertEqual(daily["thread"], "Daily")
        self.assertEqual(daily["pub_date"], TODAY.isoformat())
        self.assertEqual(
            daily["tasks"],
            [
                {"text": "alpha", "done": False},
                {"text": "bravo", "done": True},
                {"text": "charlie", "done": False},
            ],
        )

    def test_weekly_and_monthly_use_period_end_dates(self):
        eow = make_last_day_of_the_week(TODAY)
        eom = make_last_day_of_the_month(TODAY)
        Plan.objects.create(pub_date=eow, thread=self.weekly, focus="week task")
        Plan.objects.create(pub_date=eom, thread=self.bigpic, focus="month task")
        Reflection.objects.create(pub_date=eom, thread=self.bigpic, good="month task")

        body = self._get().json()

        self.assertEqual(body["weekly"]["thread"], "Weekly")
        self.assertEqual(body["weekly"]["pub_date"], eow.isoformat())
        self.assertEqual(
            body["weekly"]["tasks"], [{"text": "week task", "done": False}]
        )

        self.assertEqual(body["monthly"]["thread"], "Big-picture")
        self.assertEqual(body["monthly"]["pub_date"], eom.isoformat())
        self.assertEqual(
            body["monthly"]["tasks"], [{"text": "month task", "done": True}]
        )

    def test_empty_when_nothing_planned(self):
        body = self._get().json()
        self.assertEqual(body["daily"]["tasks"], [])
        self.assertEqual(body["weekly"]["tasks"], [])
        self.assertEqual(body["monthly"]["tasks"], [])

    def test_defaults_to_server_today_without_date_param(self):
        resp = self._get(date_str=None)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("daily", resp.json())

    def test_bad_date_returns_400(self):
        resp = self._get(date_str="not-a-date")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
