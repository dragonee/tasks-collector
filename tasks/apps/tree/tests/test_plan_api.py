from datetime import date as date_cls

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Plan, Reflection, Thread
from .factories import make_thread

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
        cls.daily = make_thread(cls.user, "Daily")
        cls.weekly = make_thread(cls.user, "Weekly")
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
        cls.daily = make_thread(cls.user, "Daily")
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

        # Nothing to add: the plan is left as it was.
        self.assertEqual(self._add_today("a").focus, "a\r\nb")

    def test_new_line_appended_to_crlf_plan(self):
        Plan.objects.create(
            pub_date=date_cls.today(), thread=self.daily, focus="a\r\nb"
        )

        self.assertEqual(self._add_today("c").focus, "a\nb\nc")

    def test_the_callers_date_decides_which_day_is_today(self):
        # Late evening for the caller, already tomorrow on the server (UTC),
        # or the other way round: the plan is the one for their day.
        for timeframe, thread, pub_date in (
            ("today", "Daily", "2026-03-04"),
            ("tomorrow", "Daily", "2026-03-05"),
            ("this_week", "Weekly", "2026-03-08"),
        ):
            with self.subTest(timeframe=timeframe):
                resp = self.client.post(
                    self.url,
                    {"text": "x", "timeframe": timeframe, "date": "2026-03-04"},
                    format="json",
                )

                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertEqual(resp.json()["plan_date"], pub_date)
                self.assertTrue(
                    Plan.objects.filter(
                        pub_date=pub_date,
                        thread=make_thread(self.user, thread),
                        focus="x",
                    ).exists()
                )

    def test_a_malformed_date_is_refused(self):
        resp = self.client.post(
            self.url,
            {"text": "x", "timeframe": "today", "date": "4 March"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Plan.objects.exists())


class PlanAndReflectionCreateTestCase(APITestCase):
    """plans/ and reflections/ create on one of the caller's threads, named
    as the journal API names it; they used to fail with a server error, the
    serializers having no thread."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.other = User.objects.create_user(username="o", password="x")
        make_thread(cls.other, "Theirs")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_creates_on_the_named_thread_of_the_caller(self):
        for url, model, field in (
            ("/plans/", Plan, "focus"),
            ("/reflections/", Reflection, "good"),
        ):
            with self.subTest(url=url):
                resp = self.client.post(
                    url,
                    {"pub_date": "2026-11-11", field: "x", "thread": "Daily"},
                    format="json",
                )

                self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
                self.assertNotIn("thread", resp.json())
                created = model.objects.get(pk=resp.json()["id"])
                self.assertEqual(created.thread, Thread.objects.daily(self.user))

    def test_without_a_thread_of_the_caller_it_is_refused(self):
        for url, model in (("/plans/", Plan), ("/reflections/", Reflection)):
            for thread in ({}, {"thread": "Theirs"}):
                with self.subTest(url=url, thread=thread):
                    resp = self.client.post(
                        url, {"pub_date": "2026-11-11", **thread}, format="json"
                    )

                    self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn("thread", resp.json())
        self.assertFalse(Plan.objects.exists())
        self.assertFalse(Reflection.objects.exists())

    def test_a_second_one_for_the_same_thread_and_date_is_refused(self):
        for url, model, field in (
            ("/plans/", Plan, "focus"),
            ("/reflections/", Reflection, "good"),
        ):
            with self.subTest(url=url):
                payload = {"pub_date": "2026-11-11", field: "x", "thread": "Daily"}
                self.client.post(url, payload, format="json")

                resp = self.client.post(url, payload, format="json")

                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(model.objects.count(), 1)
