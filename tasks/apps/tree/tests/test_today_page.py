import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Plan, Reflection
from ..views_today import save_or_remove_object_if_empty
from .factories import make_thread

DAY = datetime.date(2026, 11, 11)


class TodayPageSaveTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = make_thread(cls.user, "Daily")

    def setUp(self):
        self.client.force_login(self.user)

    def _post(self, **fields):
        data = {
            "thread": "Daily",
            "today_plan-focus": "",
            "tomorrow_plan-focus": "",
            "reflection-good": "",
            "reflection-better": "",
            "reflection-best": "",
            **fields,
        }
        return self.client.post(
            reverse("public-today") + f"?date={DAY}&thread=Daily", data
        )

    def test_saves_the_plans_and_the_reflection(self):
        response = self._post(
            **{
                "today_plan-focus": "water plants",
                "tomorrow_plan-focus": "call bank",
                "reflection-good": "slept well",
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Plan.objects.get(thread=self.daily, pub_date=DAY).focus, "water plants"
        )
        self.assertEqual(
            Plan.objects.get(
                thread=self.daily, pub_date=DAY + datetime.timedelta(days=1)
            ).focus,
            "call bank",
        )
        self.assertEqual(
            Reflection.objects.get(thread=self.daily, pub_date=DAY).good, "slept well"
        )

    def test_saving_twice_keeps_one_row_per_day(self):
        self._post(**{"today_plan-focus": "a"})
        self._post(**{"today_plan-focus": "a\r\nb"})

        plan = Plan.objects.get(thread=self.daily, pub_date=DAY)
        self.assertEqual(plan.focus, "a\r\nb")

    def test_emptying_a_plan_removes_it(self):
        self._post(**{"today_plan-focus": "a"})
        self._post()

        self.assertFalse(Plan.objects.filter(thread=self.daily).exists())


class SaveTheOneForItsDayTestCase(TestCase):
    """A plan or reflection loaded as "none yet" is saved after another
    request made the row: the text goes into that row."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = make_thread(cls.user, "Daily")

    def test_a_plan_made_meanwhile_is_updated(self):
        loaded = Plan(thread=self.daily, pub_date=DAY)
        existing = Plan.objects.create(thread=self.daily, pub_date=DAY, focus="phone")

        loaded.focus = "web"
        save_or_remove_object_if_empty(loaded, ["focus"])

        self.assertEqual(loaded.pk, existing.pk)
        self.assertEqual(Plan.objects.get(thread=self.daily, pub_date=DAY).focus, "web")

    def test_a_reflection_made_meanwhile_is_updated(self):
        loaded = Reflection(thread=self.daily, pub_date=DAY)
        existing = Reflection.objects.create(
            thread=self.daily, pub_date=DAY, good="phone"
        )

        loaded.good = "web"
        save_or_remove_object_if_empty(loaded, ["good", "better", "best"])

        self.assertEqual(loaded.pk, existing.pk)
        self.assertEqual(Reflection.objects.count(), 1)
