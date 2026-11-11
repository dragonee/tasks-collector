import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Plan, Reflection, Task
from ..services.tasks.documents import DocumentEdit
from ..services.today import plan_tasks, set_task_done
from ..views_today import save_document
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


class TodayPageTasksTestCase(TestCase):
    """What is written into a plan on the page becomes tasks."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = make_thread(cls.user, "Daily")

    def setUp(self):
        self.client.force_login(self.user)
        # Plans of days gone by don't make tasks: stay on the current day.
        self.today = datetime.date.today()
        self.tomorrow = self.today + datetime.timedelta(days=1)

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
            reverse("public-today") + f"?date={self.today}&thread=Daily", data
        )

    def _tasks(self, day):
        return [t for t in plan_tasks(self.user, day, "Daily")]

    def test_each_line_of_a_plan_is_a_task(self):
        self._post(**{"today_plan-focus": "water plants\r\n---\r\ncall bank"})

        self.assertEqual(
            sorted(Task.objects.values_list("text", flat=True)),
            ["call bank", "water plants"],
        )
        # The separator is a line, not something to do.
        plan = Plan.objects.get(thread=self.daily, pub_date=self.today)
        self.assertEqual(plan.focus, "water plants\r\n---\r\ncall bank")
        self.assertEqual(
            [bool(task.id) for task in self._tasks(self.today)], [True, False, True]
        )

    def test_saving_the_same_text_again_keeps_the_tasks(self):
        self._post(**{"today_plan-focus": "water plants\r\ncall bank"})
        ids = set(Task.objects.values_list("pk", flat=True))

        self._post(**{"today_plan-focus": "water plants\r\ncall bank"})

        self.assertEqual(set(Task.objects.values_list("pk", flat=True)), ids)

    def test_rewording_a_line_renames_its_task(self):
        self._post(**{"today_plan-focus": "water plants\r\ncall bank"})
        task = Task.objects.get(text="call bank")

        self._post(**{"today_plan-focus": "water plants\r\ncall the bank"})

        task.refresh_from_db()
        self.assertEqual(task.text, "call the bank")
        self.assertEqual(Task.objects.count(), 2)

    def test_removing_a_line_forgets_a_task_nothing_remembers(self):
        self._post(**{"today_plan-focus": "water plants\r\ncall bank"})

        self._post(**{"today_plan-focus": "water plants"})

        self.assertEqual(
            list(Task.objects.values_list("text", flat=True)), ["water plants"]
        )

    def test_a_done_task_stays_when_its_line_is_removed(self):
        self._post(**{"today_plan-focus": "call bank"})
        set_task_done(self.user, "call bank", True, today=self.today)

        self._post(**{"reflection-good": "call bank"})

        task = Task.objects.get()
        self.assertTrue(task.done)
        self.assertFalse(Plan.objects.filter(thread=self.daily).exists())

    def test_a_line_moved_to_tomorrow_is_the_same_task(self):
        self._post(**{"today_plan-focus": "water plants\r\ncall bank"})
        task = Task.objects.get(text="call bank")

        self._post(
            **{"today_plan-focus": "water plants", "tomorrow_plan-focus": "call bank"}
        )

        self.assertEqual(Task.objects.count(), 2)
        (line,) = task.plan_lines.all()
        self.assertEqual(line.plan.pub_date, self.tomorrow)

    def test_a_reworded_reflection_line_keeps_its_task(self):
        self._post(**{"today_plan-focus": "call bank"})
        set_task_done(self.user, "call bank", True, today=self.today)

        self._post(
            **{
                "today_plan-focus": "call bank",
                "reflection-good": "slept well\r\ncall bank, sorted at last",
                "reflection-best": "start earlier",
            }
        )

        reflection = Reflection.objects.get(thread=self.daily, pub_date=self.today)
        self.assertEqual(reflection.good, "slept well\r\ncall bank, sorted at last")
        self.assertEqual(reflection.best, "start earlier")
        lines = {line.text: line.task for line in reflection.lines.all()}
        self.assertEqual(lines["call bank, sorted at last"], Task.objects.get())
        self.assertIsNone(lines["slept well"])
        self.assertIsNone(lines["start earlier"])
        # Rewording the reflection doesn't touch the task.
        self.assertEqual(Task.objects.get().text, "call bank")

    def test_a_plan_of_a_day_gone_by_makes_no_tasks(self):
        long_ago = self.today - datetime.timedelta(days=30)

        self.client.post(
            reverse("public-today") + f"?date={long_ago}&thread=Daily",
            {
                "thread": "Daily",
                "today_plan-focus": "what I meant to do",
                "tomorrow_plan-focus": "",
                "reflection-good": "",
                "reflection-better": "",
                "reflection-best": "",
            },
        )

        self.assertEqual(
            Plan.objects.get(thread=self.daily, pub_date=long_ago).focus,
            "what I meant to do",
        )
        self.assertFalse(Task.objects.exists())


class SaveTheOneForItsDayTestCase(TestCase):
    """A plan or reflection loaded as "none yet" is saved after another
    request made the row: the text goes into that row."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = make_thread(cls.user, "Daily")

    def _save(self, document):
        edit = DocumentEdit()
        save_document(edit, document)
        edit.finish()

    def test_a_plan_made_meanwhile_is_updated(self):
        loaded = Plan(thread=self.daily, pub_date=DAY)
        existing = Plan.objects.create(thread=self.daily, pub_date=DAY, focus="phone")

        loaded.focus = "web"
        self._save(loaded)

        self.assertEqual(loaded.pk, existing.pk)
        self.assertEqual(Plan.objects.get(thread=self.daily, pub_date=DAY).focus, "web")

    def test_a_reflection_made_meanwhile_is_updated(self):
        loaded = Reflection(thread=self.daily, pub_date=DAY)
        existing = Reflection.objects.create(
            thread=self.daily, pub_date=DAY, good="phone"
        )

        loaded.good = "web"
        self._save(loaded)

        self.assertEqual(loaded.pk, existing.pk)
        self.assertEqual(Reflection.objects.count(), 1)
