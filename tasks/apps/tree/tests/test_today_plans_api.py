from datetime import date as date_cls

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Plan, Reflection, Task
from ..services.today import add_task, set_task_done
from ..utils.datetime import make_last_day_of_the_month, make_last_day_of_the_week
from .factories import make_thread

# A Thursday — end-of-week and end-of-month fall on distinct later dates.
TODAY = date_cls(2026, 6, 25)


def _brief(tasks):
    """What the journal template reads of each task."""
    return [{key: task[key] for key in ("text", "done", "mark")} for task in tasks]


class TodayPlansAPITestCase(APITestCase):
    """The single CLI-facing endpoint that returns the Daily / Weekly /
    Big-picture plans with each task flagged crossed-off."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = make_thread(cls.user, "Daily")
        cls.weekly = make_thread(cls.user, "Weekly")
        # Lowercase, as in the dev fixtures, the web Today view and reflection
        # extraction — the name the monthly plans are actually stored under.
        cls.bigpic = make_thread(cls.user, "big-picture")
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
            _brief(daily["tasks"]),
            [
                {"text": "alpha", "done": False, "mark": None},
                {"text": "bravo", "done": True, "mark": None},
                {"text": "charlie", "done": False, "mark": None},
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
            _brief(body["weekly"]["tasks"]),
            [{"text": "week task", "done": False, "mark": None}],
        )

        self.assertEqual(body["monthly"]["thread"], "big-picture")
        self.assertEqual(body["monthly"]["pub_date"], eom.isoformat())
        self.assertEqual(
            _brief(body["monthly"]["tasks"]),
            [{"text": "month task", "done": True, "mark": None}],
        )

    def test_crlf_stored_focus_returns_clean_task_text(self):
        # Some writers store the focus with \r\n endings; task text must come
        # back with no stray \r so the journal prints normal newlines.
        Plan.objects.create(pub_date=TODAY, thread=self.daily, focus="alpha\r\nbravo")
        Reflection.objects.create(pub_date=TODAY, thread=self.daily, good="bravo")

        tasks = self._get().json()["daily"]["tasks"]
        self.assertEqual(
            _brief(tasks),
            [
                {"text": "alpha", "done": False, "mark": None},
                {"text": "bravo", "done": True, "mark": None},
            ],
        )

    def test_a_plain_line_has_no_task_id(self):
        Plan.objects.create(pub_date=TODAY, thread=self.daily, focus="alpha")

        (task,) = self._get().json()["daily"]["tasks"]

        self.assertEqual(
            task,
            {
                "text": "alpha",
                "done": False,
                "mark": None,
                "id": None,
                "anchor": None,
                "total": 1,
                "done_count": 0,
            },
        )

    def test_a_task_of_the_week_done_on_a_day_is_done_in_the_week(self):
        # The same task on the week's and the day's plan: ticked on the day,
        # it reads done wherever it is listed.
        eow = make_last_day_of_the_week(TODAY)
        Plan.objects.create(pub_date=eow, thread=self.weekly, focus="write report (2)")
        add_task(self.user, "write report (2)", today=TODAY)
        set_task_done(self.user, "write report (2)", True, today=TODAY)
        set_task_done(self.user, "write report (2)", True, today=TODAY)
        task = Task.objects.get()

        body = self._get().json()

        expected = {
            "text": "write report (2/2)",
            "done": True,
            "mark": None,
            "id": str(task.pk),
            "anchor": task.anchor,
            "total": 2,
            "done_count": 2,
        }
        self.assertEqual(body["daily"]["tasks"], [expected])
        self.assertEqual(body["weekly"]["tasks"], [expected])

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
