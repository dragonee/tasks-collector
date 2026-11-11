"""Plans and reflections as documents of lines: the rows say what the text
columns say, and keep their tasks when the text is rewritten."""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Plan, PlanLine, Reflection, ReflectionLine, Task
from ..services.tasks import documents
from ..services.tasks.base import create_task
from ..services.tasks.operations import complete, rename
from .factories import make_thread

LONG_AGO = datetime.date(2020, 3, 4)


class DocumentTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = make_thread(cls.user, "Daily")
        cls.weekly = make_thread(cls.user, "Weekly")
        cls.side = make_thread(cls.user, "Sidetrack")
        cls.today = datetime.date.today()

    def _plan(self, focus, thread=None, pub_date=None):
        return Plan.objects.create(
            thread=thread or self.daily, pub_date=pub_date or self.today, focus=focus
        )

    def _texts(self, doc, field=None):
        return [row.content for row in documents.rows(doc, field)]


class EnsureLinesTestCase(DocumentTestCase):
    def test_text_as_history_has_it_round_trips(self):
        # CRLF, a blank line inside, separators, a trailing newline.
        for focus in (
            "a\r\nb",
            "a\n\nb",
            "-\na\n---\nb\n-",
            "a\n",
            "only",
        ):
            with self.subTest(focus=focus):
                plan = self._plan(focus, pub_date=LONG_AGO)

                documents.ensure_lines(plan)

                self.assertEqual(
                    documents.render(self._texts(plan)),
                    focus.replace("\r\n", "\n"),
                )
                # Nothing was written by the catching up.
                self.assertEqual(Plan.objects.get(pk=plan.pk).focus, focus)
                plan.delete()

    def test_an_empty_document_has_no_lines(self):
        for focus in (None, ""):
            with self.subTest(focus=focus):
                plan = self._plan(focus)
                documents.ensure_lines(plan)
                self.assertEqual(documents.rows(plan), [])
                plan.delete()

    def test_the_three_fields_of_a_reflection_are_three_lists(self):
        reflection = Reflection.objects.create(
            thread=self.daily, pub_date=self.today, good="a\nb", better=None, best="c"
        )

        documents.ensure_lines(reflection)

        self.assertEqual(self._texts(reflection, "good"), ["a", "b"])
        self.assertEqual(self._texts(reflection, "better"), [])
        self.assertEqual(self._texts(reflection, "best"), ["c"])

    def test_catching_up_makes_no_tasks(self):
        # Text that got into the column some other way (the admin, an older
        # release) becomes plain lines; only writing a plan makes tasks.
        plan = self._plan("a\nb")

        documents.ensure_lines(plan)

        self.assertFalse(Task.objects.exists())
        self.assertEqual(self._texts(plan), ["a", "b"])

    def test_catching_up_keeps_the_tasks_of_lines_still_there(self):
        plan = self._plan("a\nb")
        documents.sync_lines(plan, create_tasks=True)
        a, b = Task.objects.order_by("text")

        Plan.objects.filter(pk=plan.pk).update(focus="new\r\nb\r\na")
        plan.refresh_from_db()
        documents.ensure_lines(plan)

        # A line typed in, and "a" moved below "b": both keep their tasks.
        self.assertEqual(
            [(row.content, row.task) for row in documents.rows(plan)],
            [("new", None), ("b", b), ("a", a)],
        )
        self.assertEqual(Task.objects.count(), 2)


class WritingAPlanTestCase(DocumentTestCase):
    def test_lines_become_tasks(self):
        plan = self._plan("water plants\n\n---\ncall bank")

        documents.sync_lines(plan, create_tasks=True)

        self.assertEqual(
            [(row.content, row.task_id is not None) for row in documents.rows(plan)],
            [("water plants", True), ("", False), ("---", False), ("call bank", True)],
        )
        for task in Task.objects.all():
            self.assertEqual(task.user, self.user)
            self.assertEqual(task.event_stream_id, self.daily.board_stream_id)

    def test_not_on_a_plan_whose_period_is_over(self):
        plan = self._plan("a", pub_date=LONG_AGO)

        documents.sync_lines(plan, create_tasks=True)

        self.assertFalse(Task.objects.exists())

    def test_yesterdays_plan_still_makes_tasks(self):
        # The day page shows yesterday until noon.
        plan = self._plan("a", pub_date=self.today - datetime.timedelta(days=1))

        documents.sync_lines(plan, create_tasks=True)

        self.assertTrue(Task.objects.exists())

    def test_not_on_a_thread_that_is_not_built_in(self):
        plan = self._plan("a", thread=self.side)

        documents.sync_lines(plan, create_tasks=True)

        self.assertFalse(Task.objects.exists())

    def test_the_same_line_twice_is_two_tasks(self):
        plan = self._plan("a\na")

        documents.sync_lines(plan, create_tasks=True)

        self.assertEqual(Task.objects.count(), 2)
        self.assertEqual(self._texts(plan), ["a", "a"])

    def test_rewording_one_line_among_others(self):
        plan = self._plan("water plants\ncall bank\nbuy bread")
        documents.sync_lines(plan, create_tasks=True)
        tasks = {task.text: task.pk for task in Task.objects.all()}

        plan.focus = "buy milk\nwater the plants\ncall bank"
        plan.save()
        documents.sync_lines(plan, create_tasks=True)

        after = {row.content: row.task.pk for row in documents.rows(plan)}
        self.assertEqual(after["water the plants"], tasks["water plants"])
        self.assertEqual(after["call bank"], tasks["call bank"])
        # A line typed in, and one taken out and forgotten.
        self.assertNotIn(after["buy milk"], tasks.values())
        self.assertFalse(Task.objects.filter(pk=tasks["buy bread"]).exists())

    def test_a_renamed_task_reads_the_same_on_every_plan(self):
        day = self._plan("call bank")
        documents.sync_lines(day, create_tasks=True)
        task = Task.objects.get()
        week = Plan.objects.create(
            thread=self.weekly, pub_date=self.today + datetime.timedelta(days=7)
        )
        documents.append_task(week, task)

        rename(task, "call the bank")

        for plan in (day, week):
            self.assertEqual(Plan.objects.get(pk=plan.pk).focus, "call the bank")

        # And rewording it in one plan's text does the same.
        day.refresh_from_db()
        day.focus = "call the bank today"
        day.save()
        documents.sync_lines(day, create_tasks=True)

        self.assertEqual(Plan.objects.get(pk=week.pk).focus, "call the bank today")
        self.assertEqual(Task.objects.count(), 1)

    def test_deleting_a_plan_forgets_its_open_tasks_and_keeps_the_done(self):
        plan = self._plan("a\nb")
        documents.sync_lines(plan, create_tasks=True)
        complete(Task.objects.get(text="b"), self.user, day=self.today)

        documents.delete(plan)

        self.assertFalse(Plan.objects.exists())
        self.assertEqual([task.text for task in Task.objects.all()], ["b"])


class RewritingAReflectionTestCase(DocumentTestCase):
    def setUp(self):
        self.task = create_task(self.user, "call bank")
        self.completion = complete(self.task, self.user, day=self.today)
        self.reflection = Reflection.objects.get(thread=self.daily, pub_date=self.today)

    def _write(self, **fields):
        for field, text in fields.items():
            setattr(self.reflection, field, text)
        self.reflection.save()
        documents.sync_lines(self.reflection, create_tasks=False)

    def _line(self):
        return ReflectionLine.objects.get(task=self.task)

    def test_a_reworded_line_keeps_its_task(self):
        self._write(good="a good day\ncalled the bank\nslept well")

        line = self._line()
        self.assertEqual(line.text, "called the bank")
        self.assertEqual(line.completion, self.completion)
        self.assertEqual(ReflectionLine.objects.filter(task=None).count(), 2)
        # The wording of a reflection is its own.
        self.task.refresh_from_db()
        self.assertEqual(self.task.text, "call bank")

    def test_removing_the_line_does_not_reopen_the_task(self):
        self._write(good="slept well")

        self.assertFalse(ReflectionLine.objects.filter(task=self.task).exists())
        self.task.refresh_from_db()
        self.assertTrue(self.task.done)

    def test_a_line_moved_to_another_field_keeps_its_task(self):
        self._write(good="slept well", best="call bank")

        line = self._line()
        self.assertEqual((line.field, line.completion), ("best", self.completion))

    def test_lines_typed_in_have_no_task(self):
        self._write(good="call bank\nslept well", better="start earlier")

        self.assertEqual(
            {line.text: line.task for line in ReflectionLine.objects.all()},
            {"call bank": self.task, "slept well": None, "start earlier": None},
        )


class PlanAPITasksTestCase(APITestCase):
    """plans/ and reflections/ write text; a plan written there is tasks."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.today = datetime.date.today()

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_a_plan_made_changed_and_deleted_through_the_api(self):
        created = self.client.post(
            "/plans/",
            {"pub_date": self.today, "focus": "a\r\nb", "thread": "Daily"},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        a, b = Task.objects.order_by("text")
        plan_id = created.json()["id"]

        changed = self.client.patch(
            f"/plans/{plan_id}/", {"focus": "b\nc"}, format="json"
        )
        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row.task.text for row in PlanLine.objects.filter(plan_id=plan_id)],
            ["b", "c"],
        )
        self.assertFalse(Task.objects.filter(pk=a.pk).exists())
        self.assertTrue(Task.objects.filter(pk=b.pk).exists())

        deleted = self.client.delete(f"/plans/{plan_id}/")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.exists())

    def test_a_reflection_written_through_the_api_has_its_lines(self):
        created = self.client.post(
            "/reflections/",
            {"pub_date": self.today, "good": "a\r\nb", "thread": "Daily"},
            format="json",
        )

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            list(
                ReflectionLine.objects.order_by("position").values_list(
                    "field", "text", "task"
                )
            ),
            [("good", "a", None), ("good", "b", None)],
        )
        self.assertFalse(Task.objects.exists())
