import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Plan, Reflection, Task
from ..services.tasks import agenda, documents
from ..services.tasks import operations as tasks
from .factories import complete, make_thread, plan_task

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
        self.assertEqual(plan.focus, "a\nb")

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
        return agenda.plan_tasks(self.user, day, "Daily")

    def test_each_line_of_a_plan_is_a_task(self):
        self._post(**{"today_plan-focus": "water plants\r\n---\r\ncall bank"})

        self.assertEqual(
            sorted(Task.objects.values_list("text", flat=True)),
            ["call bank", "water plants"],
        )
        # The separator is a line, not something to do.
        plan = Plan.objects.get(thread=self.daily, pub_date=self.today)
        self.assertEqual(plan.focus, "water plants\n---\ncall bank")
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
        complete(Task.objects.get(text="call bank"), self.user, self.today)

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
        complete(Task.objects.get(text="call bank"), self.user, self.today)

        self._post(
            **{
                "today_plan-focus": "call bank",
                "reflection-good": "slept well\r\ncall bank, sorted at last",
                "reflection-best": "start earlier",
            }
        )

        reflection = Reflection.objects.get(thread=self.daily, pub_date=self.today)
        self.assertEqual(reflection.good, "slept well\ncall bank, sorted at last")
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


class TodayPageEditorTestCase(TestCase):
    """The page's editors hold text with anchors, and post it along with the
    text they loaded: only what was changed on the page is applied."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = make_thread(cls.user, "Daily")
        cls.weekly = make_thread(cls.user, "Weekly")

    def setUp(self):
        self.client.force_login(self.user)
        self.today = datetime.date.today()
        self.tomorrow = self.today + datetime.timedelta(days=1)
        self.url = reverse("public-today") + f"?date={self.today}&thread=Daily"

    def _load(self):
        """The page as a browser has it: {field name: text}, with the bases."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        editors = response.context["editors"]
        fields = {"thread": "Daily"}
        for editor in editors.values():
            fields[editor["name"]] = editor["text"]
            fields[f"{editor['name']}-base"] = editor["text"]
        return fields

    def _save(self, fields, **changes):
        response = self.client.post(self.url, {**fields, **changes})
        self.assertEqual(response.status_code, 302)

    def _plan(self, day=None):
        return Plan.objects.get(thread=self.daily, pub_date=day or self.today)

    def _task(self, text):
        return Task.objects.get(text=text)

    def test_the_page_shows_a_task_line_with_its_anchor(self):
        plan_task(self.user, "call bank", self.today)
        task = self._task("call bank")

        response = self.client.get(self.url)

        editor = response.context["editors"]["today_plan_focus"]
        self.assertEqual(editor["text"], f"call bank ^t{task.anchor}")
        self.assertContains(
            response, f'name="today_plan-focus-base" value="call bank ^t{task.anchor}"'
        )
        self.assertEqual(
            response.context["chips"],
            {
                task.anchor: {
                    "id": str(task.pk),
                    "text": "call bank",
                    "display": "call bank",
                    "done": False,
                    "total": 1,
                    "done_count": 0,
                }
            },
        )

    def test_a_reworded_line_renames_its_task_whatever_the_new_wording(self):
        plan_task(self.user, "call bank", self.today)
        task = self._task("call bank")
        page = self._load()

        self._save(
            page,
            **{"today_plan-focus": f"Ring Mr Kowalski about the loan ^t{task.anchor}"},
        )

        task.refresh_from_db()
        self.assertEqual(task.text, "Ring Mr Kowalski about the loan")
        self.assertEqual(Task.objects.count(), 1)

    def test_a_line_added_elsewhere_since_the_page_loaded_stays(self):
        plan_task(self.user, "call bank", self.today)
        page = self._load()
        # From the phone, while the page sits open in a tab.
        complete(plan_task(self.user, "buy bread", self.today), self.user, self.today)

        self._save(
            page,
            **{
                "today_plan-focus": page["today_plan-focus"] + "\r\nwater plants",
                "reflection-good": "slept well",
            },
        )

        self.assertEqual(self._plan().focus, "call bank\nwater plants\nbuy bread")
        reflection = Reflection.objects.get(thread=self.daily, pub_date=self.today)
        self.assertEqual(reflection.good, "slept well\nbuy bread")
        self.assertTrue(self._task("buy bread").done)

    def test_a_line_taken_off_elsewhere_is_not_put_back(self):
        plan_task(self.user, "call bank", self.today)
        plan_task(self.user, "buy bread", self.today)
        page = self._load()
        # Moved to tomorrow from the phone.
        tasks.move(
            self._task("buy bread"),
            self._plan(),
            documents.plan_for(self.daily, self.tomorrow, create=True),
        )

        self._save(page, **{"reflection-good": "slept well"})

        self.assertEqual(self._plan().focus, "call bank")
        self.assertEqual(self._plan(self.tomorrow).focus, "buy bread")

    def test_a_line_removed_on_the_page_goes(self):
        plan_task(self.user, "call bank", self.today)
        plan_task(self.user, "buy bread", self.today)
        bank = self._task("call bank")
        page = self._load()

        self._save(page, **{"today_plan-focus": f"call bank ^t{bank.anchor}"})

        self.assertEqual(self._plan().focus, "call bank")
        self.assertFalse(Task.objects.filter(text="buy bread").exists())

    def test_a_line_cut_from_today_and_pasted_into_tomorrow_is_the_same_task(self):
        plan_task(self.user, "call bank", self.today)
        task = self._task("call bank")
        page = self._load()

        self._save(
            page,
            **{
                "today_plan-focus": "",
                "tomorrow_plan-focus": f"call bank ^t{task.anchor}",
            },
        )

        self.assertEqual(Task.objects.get(), task)
        (line,) = task.plan_lines.all()
        self.assertEqual(line.plan.pub_date, self.tomorrow)
        self.assertFalse(Plan.objects.filter(pub_date=self.today).exists())

    def test_an_anchor_taken_off_a_plan_line_makes_it_another_task(self):
        complete(plan_task(self.user, "call bank", self.today), self.user, self.today)
        done = self._task("call bank")
        page = self._load()

        self._save(page, **{"today_plan-focus": "call bank"})

        again = Task.objects.exclude(pk=done.pk).get()
        self.assertEqual((again.text, again.done), ("call bank", False))
        # The one that was done stays, off the plan.
        done.refresh_from_db()
        self.assertTrue(done.done)
        self.assertFalse(done.plan_lines.exists())

    def test_a_reflection_line_keeps_its_task_reworded_and_moved(self):
        complete(plan_task(self.user, "call bank", self.today), self.user, self.today)
        task = self._task("call bank")
        page = self._load()
        self.assertEqual(page["reflection-good"], f"call bank ^t{task.anchor}")

        self._save(
            page,
            **{
                "reflection-good": "slept well",
                "reflection-best": f"Sorted the loan at last ^t{task.anchor}",
            },
        )

        reflection = Reflection.objects.get(thread=self.daily, pub_date=self.today)
        self.assertEqual(reflection.good, "slept well")
        self.assertEqual(reflection.best, "Sorted the loan at last")
        line = reflection.lines.get(task=task)
        self.assertEqual(line.field, "best")
        self.assertEqual(line.completion, task.completions.get())
        # The wording of a reflection is its own.
        task.refresh_from_db()
        self.assertEqual(task.text, "call bank")

    def test_an_anchor_taken_off_a_reflection_line_leaves_the_task_done(self):
        complete(plan_task(self.user, "call bank", self.today), self.user, self.today)
        task = self._task("call bank")
        page = self._load()

        self._save(page, **{"reflection-good": "call bank"})

        reflection = Reflection.objects.get(thread=self.daily, pub_date=self.today)
        self.assertEqual(reflection.good, "call bank")
        self.assertIsNone(reflection.lines.get().task)
        task.refresh_from_db()
        self.assertTrue(task.done)

    def test_an_anchor_of_someone_elses_task_is_dropped(self):
        other = get_user_model().objects.create_user(username="other", password="x")
        plan_task(other, "theirs", self.today)
        theirs = self._task("theirs")
        page = self._load()

        self._save(page, **{"today_plan-focus": f"mine ^t{theirs.anchor}"})

        self.assertEqual(self._plan().focus, "mine")
        theirs.refresh_from_db()
        self.assertEqual(theirs.text, "theirs")
        self.assertEqual(theirs.plan_lines.count(), 1)

    def test_the_weeks_plan_shows_what_is_done(self):
        sunday = self.today + datetime.timedelta(days=6 - self.today.weekday())
        week = Plan.objects.create(
            thread=self.weekly, pub_date=sunday, focus="write report\nread a book"
        )
        documents.sync_lines(week, create_tasks=True)
        complete(
            plan_task(self.user, "write report", self.today), self.user, self.today
        )

        response = self.client.get(self.url)

        (plan,) = response.context["larger_plans"]
        self.assertEqual(
            [(task.text, task.done) for task in plan["tasks"]],
            [("write report", True), ("read a book", False)],
        )
        self.assertContains(response, '<li class="done">write report</li>', html=True)
        self.assertContains(response, "<li>read a book</li>", html=True)
