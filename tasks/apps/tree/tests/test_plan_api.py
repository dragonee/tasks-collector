from datetime import date as date_cls

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Plan, Thread

# Sundays ending two consecutive weeks, and the Friday between them.
LAST_WEEK_END = date_cls(2026, 10, 25)
FRIDAY = date_cls(2026, 10, 30)
THIS_WEEK_END = date_cls(2026, 11, 1)


class PlanAPIFilterTestCase(APITestCase):
    """The generic plans/ endpoint filters by thread name and pub_date. The
    Android Today screen reads this week's plan as the first result of
    ``?thread=Weekly&pub_date=<Sunday>``, so an ignored filter surfaces
    whichever plan happens to be newest."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        cls.weekly = Thread.objects.create(name="Weekly")
        cls.url = reverse("plan-list")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _focuses(self, **params):
        resp = self.client.get(self.url, params)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return [p["focus"] for p in resp.json()["results"]]

    def test_filters_by_thread_and_pub_date(self):
        Plan.objects.create(pub_date=THIS_WEEK_END, thread=self.weekly, focus="week")
        Plan.objects.create(pub_date=THIS_WEEK_END, thread=self.daily, focus="sunday")
        Plan.objects.create(pub_date=LAST_WEEK_END, thread=self.weekly, focus="old")

        self.assertEqual(
            self._focuses(thread="Weekly", pub_date=THIS_WEEK_END.isoformat()),
            ["week"],
        )

    def test_missing_weekly_plan_returns_no_results(self):
        Plan.objects.create(pub_date=LAST_WEEK_END, thread=self.weekly, focus="old")
        Plan.objects.create(pub_date=FRIDAY, thread=self.daily, focus="friday")

        self.assertEqual(
            self._focuses(thread="Weekly", pub_date=THIS_WEEK_END.isoformat()),
            [],
        )


class PlanAddTaskTestCase(APITestCase):
    """plans/add-task/ appends a line to the plan unless it's already there.
    Plans saved through the web plan form store CRLF line endings, so the
    duplicate check must not depend on them."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        cls.url = reverse("plan-add-task")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _add_today(self, text):
        resp = self.client.post(
            self.url, {"text": text, "timeframe": "today"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return Plan.objects.get(pub_date=date_cls.today(), thread=self.daily)

    def test_creates_the_plan_with_the_task(self):
        self.assertEqual(self._add_today("water plants").focus, "water plants")

    def test_existing_line_in_crlf_plan_is_not_duplicated(self):
        Plan.objects.create(
            pub_date=date_cls.today(), thread=self.daily, focus="a\r\nb"
        )

        self.assertEqual(self._add_today("a").focus, "a\nb")

    def test_new_line_appended_to_crlf_plan(self):
        Plan.objects.create(
            pub_date=date_cls.today(), thread=self.daily, focus="a\r\nb"
        )

        self.assertEqual(self._add_today("c").focus, "a\nb\nc")
