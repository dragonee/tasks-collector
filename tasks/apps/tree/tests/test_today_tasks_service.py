import threading
from datetime import date as date_cls
from datetime import datetime as datetime_cls
from datetime import timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, TransactionTestCase
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
)
from ..services.today import (
    NoBoardError,
    add_task,
    board_tree,
    complete_task,
    delete_task,
    list_board_items,
    list_today_tasks,
    move_task,
    plan_tasks,
    set_task_done,
)
from .factories import make_board, make_profile, make_thread

TODAY = date_cls(2026, 5, 21)
PUBLISHED_AT = datetime_cls(2026, 5, 21, 15, 42, 33, tzinfo=dt_timezone.utc)


class TodayServiceTestCase(TestCase):
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

    # --- add_task -----------------------------------------------------------

    def _item(self):
        self.board.refresh_from_db()
        return self.board.state[0]

    def test_add_task_makes_a_task_and_leaves_the_board_alone(self):
        add_task(self.user, "buy bread", today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "buy bread")

        task = Task.objects.get()
        self.assertEqual(task.text, "buy bread")
        self.assertEqual(task.user, self.user)
        self.assertFalse(task.done)
        self.assertIsNone(task.board)
        # It lives in the stream of the user's default board.
        self.assertEqual(task.event_stream_id, self.daily.board_stream_id)
        self.assertEqual([line.plan for line in task.plan_lines.all()], [plan])

    def test_add_task_is_idempotent(self):
        add_task(self.user, "buy bread", today=TODAY)
        add_task(self.user, "buy bread", today=TODAY)

        self.assertEqual(Task.objects.count(), 1)
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "buy bread")

    def test_add_task_plans_the_board_item_of_that_text(self):
        parent = create_unscheduled_task("parent")
        parent["children"] = [create_unscheduled_task("nested")]
        self.board.state = [parent]
        self.board.save()

        add_task(self.user, "nested", today=TODAY)

        # The item stays where it is, and now names its task.
        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        (nested,) = self.board.state[0]["children"]
        task = Task.objects.get()
        self.assertEqual(nested["data"]["taskId"], str(task.pk))
        self.assertEqual(task.board, self.board)
        self.assertEqual(task.board_item_id, nested["id"])
        self.assertIsNone(self.board.state[0]["data"]["taskId"])
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "nested")

    def test_planning_an_item_whose_task_is_done_makes_a_new_task(self):
        TOMORROW = date_cls(2026, 5, 22)
        self.board.state = [create_unscheduled_task("water plants")]
        self.board.save()
        add_task(self.user, "water plants", today=TODAY)
        set_task_done(self.user, "water plants", True, today=TODAY)
        done = Task.objects.get()

        add_task(self.user, "water plants", today=TOMORROW)

        again = Task.objects.exclude(pk=done.pk).get()
        self.assertFalse(again.done)
        self.assertEqual(self._item()["data"]["taskId"], str(again.pk))
        # The one that was done stays, with what it did.
        done.refresh_from_db()
        self.assertTrue(done.done)
        self.assertEqual(done.completions.count(), 1)

    def test_add_task_takes_the_task_from_the_weeks_plan(self):
        # A line of the week's plan pulled into a day is one task on both;
        # done on the day, it is done on the week.
        weekly = make_thread(self.user, "Weekly")
        SUNDAY = date_cls(2026, 5, 24)
        Plan.objects.create(pub_date=SUNDAY, thread=weekly, focus="write report")

        add_task(self.user, "write report", today=TODAY)
        set_task_done(self.user, "write report", True, today=TODAY)

        task = Task.objects.get()
        self.assertEqual(
            sorted(line.plan.thread.name for line in task.plan_lines.all()),
            ["Daily", "Weekly"],
        )
        (in_the_week,) = plan_tasks(self.user, SUNDAY, "Weekly")
        self.assertTrue(in_the_week.done)
        self.assertEqual(in_the_week.id, str(task.pk))

    # --- add_task: counted tasks named by the step they are on --------------

    def test_add_progress_display_form_names_the_same_task(self):
        # "Copy to today" hands the display form back to /add: it is the
        # task already planned, steps and all, not a new one.
        TOMORROW = date_cls(2026, 5, 22)
        add_task(self.user, "New task (3)", today=TODAY)
        set_task_done(self.user, "New task (3)", True, today=TODAY)

        add_task(self.user, "New task (2/3)", today=TOMORROW)

        task = Task.objects.get()
        self.assertEqual(task.done_count, 1)
        tomorrow_plan = Plan.objects.get(pub_date=TOMORROW, thread=self.daily)
        self.assertEqual(tomorrow_plan.focus, "New task (3)")
        (shown,) = list_today_tasks(self.user, today=TOMORROW)
        self.assertEqual((shown.text, shown.done), ("New task (2/3)", False))

    def test_add_progress_display_form_of_nothing_planned_starts_partway(self):
        add_task(self.user, "New task (2/3)", today=TODAY)

        task = Task.objects.get()
        self.assertEqual(task.text, "New task (3)")
        self.assertEqual(task.done_count, 1)
        (shown,) = list_today_tasks(self.user, today=TODAY)
        self.assertEqual(shown.text, "New task (2/3)")

    def test_add_progress_is_idempotent(self):
        add_task(self.user, "New task (2/3)", today=TODAY)
        add_task(self.user, "New task (2/3)", today=TODAY)

        self.assertEqual(Task.objects.count(), 1)
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "New task (3)")

    def test_add_progress_plans_the_counted_board_item(self):
        self.board.state = [create_unscheduled_task("Buy (5) apples")]
        self.board.save()

        add_task(self.user, "Buy (2/5) apples", today=TODAY)

        task = Task.objects.get()
        self.assertEqual(task.text, "Buy (5) apples")
        self.assertEqual(self._item()["data"]["taskId"], str(task.pk))
        # The item's text is not rewritten: the steps are the task's.
        self.assertEqual(self._item()["text"], "Buy (5) apples")

    def test_move_progress_task_to_tomorrow(self):
        # The task was added and one step ticked, so today's list shows it as
        # (2/3). Moving hands that display form to /move.
        TOMORROW = date_cls(2026, 5, 22)
        add_task(self.user, "New task (3)", today=TODAY)
        set_task_done(self.user, "New task (3)", True, today=TODAY)

        move_task(self.user, "New task (2/3)", TODAY, TOMORROW)

        # It is the same task tomorrow, one step in; today's line is gone.
        self.assertEqual(Task.objects.count(), 1)
        tomorrow_plan = Plan.objects.get(pub_date=TOMORROW, thread=self.daily)
        self.assertEqual(tomorrow_plan.focus, "New task (3)")
        today_plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(today_plan.focus, "")
        (shown,) = list_today_tasks(self.user, today=TOMORROW)
        self.assertEqual((shown.text, shown.done), ("New task (2/3)", False))

        # Today keeps its record of the step done that day.
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "New task (1)")

    # --- set_task_done ------------------------------------------------------

    def test_set_task_done_completes_the_task_and_appends_reflection(self):
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)

        task = Task.objects.get()
        self.assertTrue(task.done)
        self.assertIsNotNone(task.completed_at)
        completion = TaskCompleted.objects.get()
        self.assertEqual(completion.task, task)
        self.assertEqual(completion.day, TODAY)
        self.assertEqual(completion.created_by, self.user)
        self.assertEqual(completion.event_stream_id, task.event_stream_id)

        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")
        line = ReflectionLine.objects.get()
        self.assertEqual((line.task, line.completion), (task, completion))

    def test_set_task_done_ticks_the_board_item_of_the_task(self):
        self.board.state = [create_unscheduled_task("buy bread")]
        self.board.save()
        add_task(self.user, "buy bread", today=TODAY)

        set_task_done(self.user, "buy bread", True, today=TODAY)

        self.assertEqual(self._item()["data"]["state"], "done")
        # The Vue Board view renders a node as checked from this flag.
        self.assertTrue(self._item()["state"]["checked"])

    def test_set_task_done_false_reopens_and_unticks(self):
        self.board.state = [create_unscheduled_task("buy bread")]
        self.board.save()
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)

        set_task_done(self.user, "buy bread", False, today=TODAY)

        task = Task.objects.get()
        self.assertFalse(task.done)
        self.assertIsNone(task.completed_at)
        self.assertFalse(TaskCompleted.objects.exists())
        self.assertEqual(self._item()["data"]["state"], "open")
        self.assertFalse(self._item()["state"]["checked"])

    def test_set_task_done_false_removes_only_that_reflection_line(self):
        add_task(self.user, "buy bread", today=TODAY)
        add_task(self.user, "walk dog", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)
        set_task_done(self.user, "walk dog", True, today=TODAY)

        set_task_done(self.user, "buy bread", False, today=TODAY)

        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "walk dog")
        self.assertFalse(Task.objects.get(text="buy bread").done)
        self.assertTrue(Task.objects.get(text="walk dog").done)

    def test_set_task_done_twice_is_done_once(self):
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)

        self.assertEqual(Task.objects.get().done_count, 1)
        self.assertEqual(TaskCompleted.objects.count(), 1)
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

    def test_set_task_done_on_unknown_text_plans_and_completes_it(self):
        set_task_done(self.user, "surprise", True, today=TODAY)

        self.assertTrue(Task.objects.get(text="surprise").done)
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "surprise")
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "surprise")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])

    def test_a_reworded_reflection_line_is_still_the_tasks(self):
        # The reflection is rewritten as text (the day page, the API); the
        # line keeps its task, and goes when the task is reopened.
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        reflection.good = "slept well\nbuy bread, rye this time"
        reflection.save()

        set_task_done(self.user, "buy bread", False, today=TODAY)

        reflection.refresh_from_db()
        self.assertEqual(reflection.good, "slept well")

    def test_a_plain_plan_line_becomes_a_task_as_done_as_it_was(self):
        # Written as text before tasks had rows: done because the reflection
        # says so. Unticking it makes it a task and takes that line back.
        Plan.objects.create(pub_date=TODAY, thread=self.daily, focus="a\nb")
        Reflection.objects.create(pub_date=TODAY, thread=self.daily, good="b\nc")
        self.assertEqual(
            [(t.text, t.done, t.id) for t in list_today_tasks(self.user, TODAY)],
            [("a", False, None), ("b", True, None)],
        )

        set_task_done(self.user, "b", False, today=TODAY)

        task = Task.objects.get()
        self.assertEqual((task.text, task.done), ("b", False))
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "c")
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "a\nb")

    # --- delete_task --------------------------------------------------------

    def test_delete_task_takes_it_off_the_plan_and_forgets_it(self):
        add_task(self.user, "buy bread", today=TODAY)
        delete_task(self.user, "buy bread", today=TODAY)

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "")
        # Nothing remembers it: never done, on no plan, not a board item.
        self.assertFalse(Task.objects.exists())

    def test_delete_task_leaves_the_board_alone(self):
        parent = create_unscheduled_task("parent")
        parent["children"] = [create_unscheduled_task("kid")]
        self.board.state = [parent, create_unscheduled_task("leaf")]
        self.board.save()
        Plan.objects.create(pub_date=TODAY, thread=self.daily, focus="parent")
        add_task(self.user, "leaf", today=TODAY)

        delete_task(self.user, "parent", today=TODAY)
        delete_task(self.user, "leaf", today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual([n["text"] for n in self.board.state], ["parent", "leaf"])
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "")
        # The item is still planned-from: its task is kept for next time.
        self.assertEqual(Task.objects.get().text, "leaf")

    def test_delete_task_keeps_a_done_task_and_its_reflection(self):
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)

        delete_task(self.user, "buy bread", today=TODAY)

        self.assertTrue(Task.objects.get().done)
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

    # --- move_task ----------------------------------------------------------

    def test_move_plain_task_is_the_same_task_on_the_other_day(self):
        TOMORROW = date_cls(2026, 5, 22)
        parent = create_unscheduled_task("Shopping")
        kid = create_unscheduled_task("buy bread")
        kid["data"]["meaningfulMarkers"]["moscow"] = "must"
        parent["children"] = [kid]
        self.board.state = [parent]
        self.board.save()
        add_task(self.user, "buy bread", today=TODAY)

        move_task(self.user, "buy bread", TODAY, TOMORROW)

        task = Task.objects.get()
        (item,) = self._item()["children"]
        self.assertEqual(item["data"]["taskId"], str(task.pk))
        self.assertEqual(item["data"]["meaningfulMarkers"]["moscow"], "must")
        today_plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(today_plan.focus, "")
        tomorrow_plan = Plan.objects.get(pub_date=TOMORROW, thread=self.daily)
        self.assertEqual(tomorrow_plan.focus, "buy bread")

    def test_move_task_leaves_other_lines_and_reflection_untouched(self):
        TOMORROW = date_cls(2026, 5, 22)
        add_task(self.user, "buy bread", today=TODAY)
        add_task(self.user, "walk dog", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)

        move_task(self.user, "buy bread", TODAY, TOMORROW)

        today_plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(today_plan.focus, "walk dog")
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

    def test_move_task_is_idempotent(self):
        # A retried request after a lost response changes nothing further.
        TOMORROW = date_cls(2026, 5, 22)
        add_task(self.user, "buy bread", today=TODAY)

        move_task(self.user, "buy bread", TODAY, TOMORROW)
        move_task(self.user, "buy bread", TODAY, TOMORROW)

        self.assertEqual(Task.objects.count(), 1)
        tomorrow_plan = Plan.objects.get(pub_date=TOMORROW, thread=self.daily)
        self.assertEqual(tomorrow_plan.focus, "buy bread")

    # --- list_today_tasks ---------------------------------------------------

    def test_list_today_tasks_sorts_unchecked_first_preserves_plan_order(self):
        for line in ("alpha", "bravo", "charlie", "delta"):
            add_task(self.user, line, today=TODAY)
        set_task_done(self.user, "alpha", True, today=TODAY)
        set_task_done(self.user, "charlie", True, today=TODAY)

        items = list_today_tasks(self.user, today=TODAY)

        # Unchecked first, in original Plan order; then checked, in order.
        self.assertEqual(
            [(it.text, it.done) for it in items],
            [
                ("bravo", False),
                ("delta", False),
                ("alpha", True),
                ("charlie", True),
            ],
        )

    def test_list_today_tasks_when_nothing_planned(self):
        self.assertEqual(list_today_tasks(self.user, today=TODAY), [])

    # --- atomicity & error path --------------------------------------------

    def test_add_task_rolls_back_when_the_plan_line_fails(self):
        with mock.patch(
            "tasks.apps.tree.services.tasks.documents.PlanLine.objects.create",
            side_effect=DatabaseError("boom"),
        ):
            with self.assertRaises(DatabaseError):
                add_task(self.user, "explode", today=TODAY)

        self.assertFalse(Task.objects.exists())
        self.assertFalse(Plan.objects.filter(pub_date=TODAY).exists())

    def test_no_board_is_needed_to_plan_and_complete_a_task(self):
        Board.objects.all().delete()

        add_task(self.user, "x", today=TODAY)
        set_task_done(self.user, "x", True, today=TODAY)

        self.assertTrue(Task.objects.get().done)
        # Only the board picker needs one.
        with self.assertRaises(NoBoardError):
            list_board_items(self.user)

    # --- journal-note modal -------------------------------------------------

    def test_check_with_note_creates_journal_entry(self):
        add_task(self.user, "buy bread", today=TODAY)

        complete_task(
            self.user,
            "buy bread",
            True,
            published=PUBLISHED_AT,
            note="bought rye instead",
        )

        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] buy bread\nbought rye instead")
        self.assertEqual(entry.published, PUBLISHED_AT)
        # Reflection.good still holds exactly one line — no duplication.
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

    def test_check_with_empty_note_creates_no_journal_entry(self):
        add_task(self.user, "buy bread", today=TODAY)

        complete_task(self.user, "buy bread", True, published=PUBLISHED_AT, note="")

        # Confirming a check with no text isn't journal-worthy — only
        # actual content gets a JournalAdded.
        self.assertFalse(JournalAdded.objects.exists())

    def test_check_without_note_creates_no_journal_entry(self):
        add_task(self.user, "buy bread", today=TODAY)

        complete_task(self.user, "buy bread", True, published=PUBLISHED_AT)

        self.assertFalse(JournalAdded.objects.exists())

    def test_uncheck_does_not_create_journal_entry(self):
        add_task(self.user, "buy bread", today=TODAY)
        complete_task(self.user, "buy bread", True, today=TODAY)
        # The first tick was without a note, so no entry exists yet.
        self.assertFalse(JournalAdded.objects.exists())

        complete_task(
            self.user,
            "buy bread",
            False,
            published=PUBLISHED_AT,
            note="should be ignored on uncheck",
        )

        self.assertFalse(JournalAdded.objects.exists())

    def test_progress_partial_journal_uses_post_tick_text(self):
        add_task(self.user, "Do tasks (3)", today=TODAY)

        complete_task(
            self.user,
            "Do tasks (3)",
            True,
            published=PUBLISHED_AT,
            note="step one done",
        )

        # Journal records the post-tick display (N=1 -> (2/3)); the count is
        # stored separately in Reflection.good.
        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] Do tasks (2/3)\nstep one done")

    def test_progress_completion_journal_matches_reflection_line(self):
        add_task(self.user, "Do tasks (3)", today=TODAY)
        # Advance to N=2 without notes.
        complete_task(self.user, "Do tasks (3)", True, today=TODAY)
        complete_task(self.user, "Do tasks (1/3)", True, today=TODAY)
        self.assertFalse(JournalAdded.objects.exists())

        # Final tick with a note completes the task (N=3).
        complete_task(
            self.user,
            "Do tasks (2/3)",
            True,
            published=PUBLISHED_AT,
            note="finished",
        )

        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] Do tasks (3/3)\nfinished")
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "Do tasks (1)\nDo tasks (2)\nDo tasks (3)")

    def test_add_another_from_complete_journals_with_overquota_text(self):
        """Ticking a fully-completed progress task keeps advancing the count
        (over-quota) and records another journal entry; the display caps at
        (M/M)."""
        add_task(self.user, "Do tasks (3)", today=TODAY)
        for old in ("Do tasks (3)", "Do tasks (1/3)", "Do tasks (2/3)"):
            complete_task(self.user, old, True, today=TODAY)
        # Now at N=3 (crossed). The above ticks carried no note → no journal yet.
        self.assertFalse(JournalAdded.objects.exists())

        complete_task(
            self.user,
            "Do tasks (3/3)",
            True,
            published=PUBLISHED_AT,
            note="one more",
        )

        # Display caps at (3/3); the count 4 is logged in the Reflection.
        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] Do tasks (3/3)\none more")
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(
            reflection.good,
            "Do tasks (1)\nDo tasks (2)\nDo tasks (3)\nDo tasks (4)",
        )

    def test_journal_failure_rolls_back_the_completion(self):
        self.board.state = [create_unscheduled_task("buy bread")]
        self.board.save()
        add_task(self.user, "buy bread", today=TODAY)

        with mock.patch(
            "tasks.apps.tree.services.tasks.operations.JournalAdded.objects.create",
            side_effect=DatabaseError("boom"),
        ):
            with self.assertRaises(DatabaseError):
                complete_task(
                    self.user,
                    "buy bread",
                    True,
                    published=PUBLISHED_AT,
                    note="boom",
                )

        # Nothing of it stays: no entry, no completion, no reflection line,
        # and the board item is still open.
        self.assertFalse(JournalAdded.objects.exists())
        self.assertFalse(TaskCompleted.objects.exists())
        self.assertFalse(Task.objects.get().done)
        reflection = Reflection.objects.filter(thread=self.daily).first()
        self.assertTrue(reflection is None or reflection.good == "")
        self.assertEqual(self._item()["data"]["state"], "open")

    # --- day lock -----------------------------------------------------------

    def _assert_day_locked_first(self, operation):
        """``operation`` row-locks the user's Daily thread before it reads the
        day's Plan or Reflection, so a concurrent write can't interleave with
        it."""
        with CaptureQueriesContext(connection) as ctx:
            operation()
        sqls = [q["sql"] for q in ctx.captured_queries]
        lock = next(
            (
                i
                for i, sql in enumerate(sqls)
                if 'FROM "tree_thread"' in sql and "FOR UPDATE" in sql
            ),
            None,
        )
        day_read = next(
            (
                i
                for i, sql in enumerate(sqls)
                if '"tree_plan"' in sql or '"tree_reflection"' in sql
            ),
            None,
        )
        self.assertIsNotNone(lock, "the day was not locked")
        self.assertIsNotNone(day_read)
        self.assertLess(lock, day_read)

    def test_writes_lock_the_day_before_reading_it(self):
        self._assert_day_locked_first(
            lambda: add_task(self.user, "buy bread", today=TODAY)
        )
        self._assert_day_locked_first(
            lambda: add_task(self.user, "Carry (2/3)", today=TODAY)
        )
        self._assert_day_locked_first(
            lambda: set_task_done(self.user, "buy bread", True, today=TODAY)
        )
        self._assert_day_locked_first(
            lambda: set_task_done(self.user, "Do tasks (3)", True, today=TODAY)
        )
        self._assert_day_locked_first(
            lambda: delete_task(self.user, "buy bread", today=TODAY)
        )
        self._assert_day_locked_first(
            lambda: move_task(self.user, "Carry (2/3)", TODAY, date_cls(2026, 5, 22))
        )


class TodayConcurrentWritesTestCase(TransactionTestCase):
    """Two Today writes in flight at once — e.g. two quick unticks on the
    phone, each its own request — must both land."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="phone", password="x")
        self.daily = make_thread(self.user, "Daily")
        make_profile(user=self.user, default_board_thread=self.daily)
        self.board = make_board(thread=self.daily, state=[])
        add_task(self.user, "buy bread", today=TODAY)
        add_task(self.user, "walk dog", today=TODAY)

    def _start(self, operation):
        """Run ``operation`` on its own thread (and so its own connection)."""
        errors = []

        def run():
            try:
                operation()
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        thread = threading.Thread(target=run)
        thread.start()
        return thread, errors

    def test_concurrent_ticks_both_land(self):
        with transaction.atomic():
            set_task_done(self.user, "buy bread", True, today=TODAY)
            # The first tick hasn't committed yet; the second must wait for it
            # rather than work from the board and reflection it saw before.
            thread, errors = self._start(
                lambda: set_task_done(self.user, "walk dog", True, today=TODAY)
            )
            thread.join(timeout=0.5)
            self.assertTrue(thread.is_alive())
        thread.join(timeout=10)

        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(
            [task.done for task in Task.objects.order_by("created")], [True, True]
        )
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread\nwalk dog")
