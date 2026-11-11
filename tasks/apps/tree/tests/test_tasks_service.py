from datetime import date as date_cls
from datetime import datetime as datetime_cls
from datetime import timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from ..board_operations import create_unscheduled_task
from ..models import (
    Board,
    JournalAdded,
    Plan,
    Reflection,
    ReflectionLine,
    Task,
    TaskCompleted,
    Thread,
)
from ..services.tasks import agenda, documents
from ..services.tasks import operations as tasks
from ..services.today import NoBoardError, board_tree, list_board_items
from ..services.today.operations import planned_task
from .factories import (
    complete,
    make_board,
    make_plan,
    make_profile,
    make_reflection,
    make_thread,
    plan_task,
)

TODAY = date_cls(2026, 5, 21)
TOMORROW = date_cls(2026, 5, 22)
PUBLISHED_AT = datetime_cls(2026, 5, 21, 15, 42, 33, tzinfo=dt_timezone.utc)


class TaskServiceTestCase(TestCase):
    """Planning a task, doing it, taking it back, moving it: what each does
    to the plans, the reflection and the board."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.daily = make_thread(cls.user, "Daily")
        make_profile(user=cls.user, default_board_thread=cls.daily)
        cls.board = make_board(thread=cls.daily, state=[])

    def setUp(self):
        # Each test gets a clean board; reload from DB so per-test mutations
        # don't leak via the cached class attribute.
        self.board = Board.objects.get(pk=self.board.pk)
        self.board.state = []
        self.board.save()
        Plan.objects.filter(thread=self.daily).delete()
        Reflection.objects.filter(thread=self.daily).delete()

    def _plan(self, text, day=TODAY):
        return plan_task(self.user, text, day)

    def _done(self, text, day=TODAY, **how):
        """Plan ``text`` for ``day`` and do a step of it."""
        return complete(self._plan(text, day), self.user, day, **how)

    def _plan_of(self, day=TODAY):
        return Plan.objects.get(pub_date=day, thread=self.daily)

    def _reflection(self, day=TODAY):
        return Reflection.objects.get(pub_date=day, thread=self.daily)

    def _shown(self, day=TODAY):
        return [
            (shown.text, shown.done)
            for shown in agenda.plan_tasks(self.user, day, Thread.DAILY)
        ]

    def _item(self):
        self.board.refresh_from_db()
        return self.board.state[0]

    # --- board items by text ------------------------------------------------

    def test_find_unscheduled_task_by_text_walks_children(self):
        deep = create_unscheduled_task("deep")
        parent = create_unscheduled_task("parent")
        parent["children"] = [deep]
        self.board.state = [create_unscheduled_task("top"), parent]
        self.board.save()
        hit = board_tree.find_unscheduled_task_by_text(self.board.state, "deep")
        self.assertIsNotNone(hit)
        _, idx, node = hit
        self.assertEqual(idx, 0)
        self.assertEqual(node["text"], "deep")

    # --- planning what was typed --------------------------------------------

    def test_a_typed_task_is_a_task_and_leaves_the_board_alone(self):
        task = self._plan("buy bread")

        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])

        plan = self._plan_of()
        self.assertEqual(plan.focus, "buy bread")

        self.assertEqual(Task.objects.get(), task)
        self.assertEqual(task.text, "buy bread")
        self.assertEqual(task.user, self.user)
        self.assertFalse(task.done)
        self.assertIsNone(task.board)
        # It lives in the stream of the user's default board.
        self.assertEqual(task.event_stream_id, self.daily.board_stream_id)
        self.assertEqual([line.plan for line in task.plan_lines.all()], [plan])

    def test_the_same_text_again_is_the_same_task(self):
        first = self._plan("buy bread")
        again = self._plan("buy bread")

        self.assertEqual(first, again)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(self._plan_of().focus, "buy bread")

    def test_text_that_names_a_board_item_plans_the_item(self):
        parent = create_unscheduled_task("parent")
        parent["children"] = [create_unscheduled_task("nested")]
        self.board.state = [parent]
        self.board.save()

        task = self._plan("nested")

        # The item stays where it is, and now names its task.
        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        (nested,) = self.board.state[0]["children"]
        self.assertEqual(nested["data"]["taskId"], str(task.pk))
        self.assertEqual(task.board, self.board)
        self.assertEqual(task.board_item_id, nested["id"])
        self.assertIsNone(self.board.state[0]["data"]["taskId"])
        self.assertEqual(self._plan_of().focus, "nested")

    def test_planning_an_item_whose_task_is_done_makes_a_new_task(self):
        self.board.state = [create_unscheduled_task("water plants")]
        self.board.save()
        done = self._done("water plants")

        again = self._plan("water plants", TOMORROW)

        self.assertNotEqual(again, done)
        self.assertFalse(again.done)
        self.assertEqual(self._item()["data"]["taskId"], str(again.pk))
        # The one that was done stays, with what it did.
        done.refresh_from_db()
        self.assertTrue(done.done)
        self.assertEqual(done.completions.count(), 1)

    def test_a_line_of_the_week_pulled_into_a_day_is_one_task(self):
        # Done on the day, it is done on the week.
        weekly = make_thread(self.user, "Weekly")
        SUNDAY = date_cls(2026, 5, 24)
        make_plan(weekly, SUNDAY, "write report")

        task = self._done("write report")

        self.assertEqual(Task.objects.get(), task)
        self.assertEqual(
            sorted(line.plan.thread.name for line in task.plan_lines.all()),
            ["Daily", "Weekly"],
        )
        (in_the_week,) = agenda.plan_tasks(self.user, SUNDAY, "Weekly")
        self.assertTrue(in_the_week.done)
        self.assertEqual(in_the_week.id, str(task.pk))

    # --- counted tasks named by the step they are on ------------------------

    def test_a_counted_task_named_by_its_step_is_the_same_task(self):
        # A list shows "New task (2/3)"; typed as shown on another day it is
        # the task already planned, steps and all, not a new one.
        task = self._done("New task (3)")

        again = self._plan("New task (2/3)", TOMORROW)

        self.assertEqual(again, task)
        self.assertEqual(again.done_count, 1)
        self.assertEqual(self._plan_of(TOMORROW).focus, "New task (3)")
        self.assertEqual(self._shown(TOMORROW), [("New task (2/3)", False)])

    def test_a_step_of_nothing_planned_starts_the_task_partway(self):
        task = self._plan("New task (2/3)")

        self.assertEqual(task.text, "New task (3)")
        self.assertEqual(task.done_count, 1)
        self.assertEqual(self._shown(), [("New task (2/3)", False)])

    def test_a_step_typed_twice_is_one_task(self):
        self._plan("New task (2/3)")
        self._plan("New task (2/3)")

        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(self._plan_of().focus, "New task (3)")

    def test_a_step_names_the_counted_board_item(self):
        self.board.state = [create_unscheduled_task("Buy (5) apples")]
        self.board.save()

        task = self._plan("Buy (2/5) apples")

        self.assertEqual(task.text, "Buy (5) apples")
        self.assertEqual(self._item()["data"]["taskId"], str(task.pk))
        # The item's text is not rewritten: the steps are the task's.
        self.assertEqual(self._item()["text"], "Buy (5) apples")

    # --- doing a task, and taking it back -----------------------------------

    def test_completing_records_an_event_and_a_reflection_line(self):
        task = self._done("buy bread")

        self.assertTrue(task.done)
        self.assertIsNotNone(task.completed_at)
        completion = TaskCompleted.objects.get()
        self.assertEqual(completion.task, task)
        self.assertEqual(completion.day, TODAY)
        self.assertEqual(completion.created_by, self.user)
        self.assertEqual(completion.event_stream_id, task.event_stream_id)

        self.assertEqual(self._reflection().good, "buy bread")
        line = ReflectionLine.objects.get()
        self.assertEqual((line.task, line.completion), (task, completion))

    def test_completing_ticks_the_board_item_of_the_task(self):
        self.board.state = [create_unscheduled_task("buy bread")]
        self.board.save()

        self._done("buy bread")

        self.assertEqual(self._item()["data"]["state"], "done")
        # The Vue Board view renders a node as checked from this flag.
        self.assertTrue(self._item()["state"]["checked"])

    def test_reopening_takes_the_step_back_and_unticks(self):
        self.board.state = [create_unscheduled_task("buy bread")]
        self.board.save()
        task = self._done("buy bread")

        self.assertTrue(tasks.reopen(task))

        task.refresh_from_db()
        self.assertFalse(task.done)
        self.assertIsNone(task.completed_at)
        self.assertFalse(TaskCompleted.objects.exists())
        self.assertEqual(self._item()["data"]["state"], "open")
        self.assertFalse(self._item()["state"]["checked"])

    def test_reopening_removes_only_that_tasks_reflection_line(self):
        bread = self._done("buy bread")
        dog = self._done("walk dog")

        tasks.reopen(bread)

        self.assertEqual(self._reflection().good, "walk dog")
        bread.refresh_from_db()
        dog.refresh_from_db()
        self.assertFalse(bread.done)
        self.assertTrue(dog.done)

    def test_a_task_without_steps_is_done_once(self):
        task = self._done("buy bread")
        complete(task, self.user, TODAY)

        self.assertEqual(task.done_count, 1)
        self.assertEqual(TaskCompleted.objects.count(), 1)
        self.assertEqual(self._reflection().good, "buy bread")

    def test_reopening_a_task_nothing_was_done_on_does_nothing(self):
        task = self._plan("buy bread")

        self.assertFalse(tasks.reopen(task))

        self.assertFalse(Reflection.objects.filter(thread=self.daily).exists())

    def test_a_reworded_reflection_line_is_still_the_tasks(self):
        # The reflection is rewritten as text (the day page, the API); the
        # line keeps its task, and goes when the task is reopened.
        task = self._done("buy bread")
        reflection = self._reflection()
        documents.write(reflection, {"good": "slept well\nbuy bread, rye this time"})

        tasks.reopen(task)

        self.assertEqual(reflection.good, "slept well")

    def test_a_plain_plan_line_becomes_a_task_as_done_as_it_was(self):
        # Written as text before tasks had rows: done because the reflection
        # says so. Named by its text it becomes a task, done; taking that
        # back takes the reflection's line.
        make_plan(self.daily, TODAY, "a\nb")
        make_reflection(self.daily, TODAY, good="b\nc")
        self.assertEqual(
            [
                (shown.text, shown.done, shown.id)
                for shown in agenda.plan_tasks(self.user, TODAY, Thread.DAILY)
            ],
            [("a", False, None), ("b", True, None)],
        )

        task = planned_task(self.user, "b", TODAY)

        self.assertEqual(Task.objects.get(), task)
        self.assertEqual((task.text, task.done), ("b", True))

        tasks.reopen(task)

        task.refresh_from_db()
        self.assertFalse(task.done)
        self.assertEqual(self._reflection().good, "c")
        self.assertEqual(self._plan_of().focus, "a\nb")

    # --- taking a task off a plan -------------------------------------------

    def test_a_task_taken_off_its_only_plan_is_forgotten(self):
        task = self._plan("buy bread")

        tasks.unplan(task, self._plan_of())

        self.assertEqual(self._plan_of().focus, "")
        # Nothing remembers it: never done, on no plan, not a board item.
        self.assertFalse(Task.objects.exists())

    def test_taking_a_task_off_a_plan_leaves_the_board_alone(self):
        parent = create_unscheduled_task("parent")
        parent["children"] = [create_unscheduled_task("kid")]
        self.board.state = [parent, create_unscheduled_task("leaf")]
        self.board.save()
        task = self._plan("leaf")

        tasks.unplan(task, self._plan_of())

        self.board.refresh_from_db()
        self.assertEqual([n["text"] for n in self.board.state], ["parent", "leaf"])
        self.assertEqual(self._plan_of().focus, "")
        # The item is still planned-from: its task is kept for next time.
        self.assertEqual(Task.objects.get().text, "leaf")

    def test_a_done_task_taken_off_a_plan_stays_with_its_reflection(self):
        task = self._done("buy bread")

        tasks.unplan(task, self._plan_of())

        self.assertTrue(Task.objects.get().done)
        self.assertEqual(self._reflection().good, "buy bread")

    # --- moving a task to another day ---------------------------------------

    def _move(self, task, from_day=TODAY, to_day=TOMORROW):
        tasks.move(
            task,
            self._plan_of(from_day),
            documents.plan_for(self.daily, to_day, create=True),
        )

    def test_a_moved_task_is_the_same_task_on_the_other_day(self):
        parent = create_unscheduled_task("Shopping")
        kid = create_unscheduled_task("buy bread")
        kid["data"]["meaningfulMarkers"]["moscow"] = "must"
        parent["children"] = [kid]
        self.board.state = [parent]
        self.board.save()
        task = self._plan("buy bread")

        self._move(task)

        self.assertEqual(Task.objects.get(), task)
        (item,) = self._item()["children"]
        self.assertEqual(item["data"]["taskId"], str(task.pk))
        self.assertEqual(item["data"]["meaningfulMarkers"]["moscow"], "must")
        self.assertEqual(self._plan_of(TODAY).focus, "")
        self.assertEqual(self._plan_of(TOMORROW).focus, "buy bread")

    def test_moving_leaves_other_lines_and_the_reflection_alone(self):
        task = self._done("buy bread")
        self._plan("walk dog")

        self._move(task)

        self.assertEqual(self._plan_of(TODAY).focus, "walk dog")
        self.assertEqual(self._reflection().good, "buy bread")

    def test_a_counted_task_moves_with_the_steps_done(self):
        task = self._done("New task (3)")

        self._move(task)

        # It is the same task tomorrow, one step in; today's line is gone.
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(self._plan_of(TOMORROW).focus, "New task (3)")
        self.assertEqual(self._plan_of(TODAY).focus, "")
        self.assertEqual(self._shown(TOMORROW), [("New task (2/3)", False)])
        # Today keeps its record of the step done that day.
        self.assertEqual(self._reflection().good, "New task (1)")

    # --- what a plan shows --------------------------------------------------

    def test_a_plan_shows_its_tasks_in_its_order(self):
        for line in ("alpha", "bravo", "charlie"):
            self._plan(line)
        complete(Task.objects.get(text="bravo"), self.user, TODAY)

        self.assertEqual(
            self._shown(),
            [("alpha", False), ("bravo", True), ("charlie", False)],
        )

    def test_nothing_planned_shows_nothing(self):
        self.assertEqual(self._shown(), [])

    # --- atomicity & error path --------------------------------------------

    def test_planning_rolls_back_when_the_plan_line_fails(self):
        with mock.patch(
            "tasks.apps.tree.services.tasks.documents.PlanLine.objects.create",
            side_effect=DatabaseError("boom"),
        ):
            with self.assertRaises(DatabaseError):
                self._plan("explode")

        self.assertFalse(Task.objects.exists())
        self.assertFalse(Plan.objects.filter(pub_date=TODAY).exists())

    def test_no_board_is_needed_to_plan_and_complete_a_task(self):
        Board.objects.all().delete()

        task = self._done("x")

        self.assertTrue(task.done)
        # Only the board picker needs one.
        with self.assertRaises(NoBoardError):
            list_board_items(self.user)

    # --- a completion with a note -------------------------------------------

    def test_a_note_makes_a_journal_entry(self):
        self._done("buy bread", at=PUBLISHED_AT, note="bought rye instead")

        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] buy bread\nbought rye instead")
        self.assertEqual(entry.published, PUBLISHED_AT)
        # The reflection still holds exactly one line: the entry is not read
        # as another completion.
        self.assertEqual(self._reflection().good, "buy bread")

    def test_an_empty_note_makes_no_journal_entry(self):
        self._done("buy bread", at=PUBLISHED_AT, note="")

        self.assertFalse(JournalAdded.objects.exists())

    def test_no_note_makes_no_journal_entry(self):
        self._done("buy bread", at=PUBLISHED_AT)

        self.assertFalse(JournalAdded.objects.exists())

    def test_a_step_is_journalled_as_the_task_then_shows(self):
        self._done("Do tasks (3)", at=PUBLISHED_AT, note="step one done")

        # One step done, so lists now show (2/3); the reflection has the
        # step itself.
        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] Do tasks (2/3)\nstep one done")

    def test_the_last_step_is_journalled_as_done(self):
        task = self._done("Do tasks (3)")
        complete(task, self.user, TODAY)
        self.assertFalse(JournalAdded.objects.exists())

        complete(task, self.user, TODAY, at=PUBLISHED_AT, note="finished")

        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] Do tasks (3/3)\nfinished")
        self.assertEqual(
            self._reflection().good, "Do tasks (1)\nDo tasks (2)\nDo tasks (3)"
        )

    def test_a_step_past_the_total_is_journalled_at_the_total(self):
        """A step of a counted task that is done still counts ("add
        another"); what lists show stops at (M/M)."""
        task = self._plan("Do tasks (3)")
        for _ in range(3):
            complete(task, self.user, TODAY)
        self.assertFalse(JournalAdded.objects.exists())

        complete(task, self.user, TODAY, at=PUBLISHED_AT, note="one more")

        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] Do tasks (3/3)\none more")
        self.assertEqual(
            self._reflection().good,
            "Do tasks (1)\nDo tasks (2)\nDo tasks (3)\nDo tasks (4)",
        )

    def test_a_failing_journal_entry_rolls_back_the_completion(self):
        self.board.state = [create_unscheduled_task("buy bread")]
        self.board.save()
        task = self._plan("buy bread")

        with mock.patch(
            "tasks.apps.tree.services.tasks.operations.JournalAdded.objects.create",
            side_effect=DatabaseError("boom"),
        ):
            with self.assertRaises(DatabaseError):
                tasks.complete(task, self.user, day=TODAY, at=PUBLISHED_AT, note="boom")

        # Nothing of it stays: no entry, no completion, no reflection line,
        # and the board item is still open.
        self.assertFalse(JournalAdded.objects.exists())
        self.assertFalse(TaskCompleted.objects.exists())
        self.assertFalse(Task.objects.get().done)
        reflection = Reflection.objects.filter(thread=self.daily).first()
        self.assertTrue(reflection is None or reflection.good == "")
        self.assertEqual(self._item()["data"]["state"], "open")

    # --- day lock -----------------------------------------------------------

    def test_planning_locks_the_day_before_reading_it(self):
        """Planning row-locks the user's Daily thread before it reads the
        day's plan, so a concurrent write can't interleave with it."""
        for text in ("buy bread", "Carry (2/3)"):
            with CaptureQueriesContext(connection) as ctx:
                self._plan(text)
            sqls = [q["sql"] for q in ctx.captured_queries]
            lock = next(
                i
                for i, sql in enumerate(sqls)
                if 'FROM "tree_thread"' in sql and "FOR UPDATE" in sql
            )
            day_read = next(i for i, sql in enumerate(sqls) if '"tree_plan"' in sql)
            self.assertLess(lock, day_read)
