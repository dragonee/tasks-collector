from datetime import date as date_cls
from datetime import datetime as datetime_cls
from datetime import timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase

from ..board_operations import create_task_item
from ..models import Board, JournalAdded, Plan, Profile, Reflection, Thread
from ..services.today import (
    NoBoardError,
    add_task,
    board_tree,
    complete_task,
    delete_task,
    list_today_tasks,
    set_task_done,
    text_lines,
)

TODAY = date_cls(2026, 5, 21)
PUBLISHED_AT = datetime_cls(2026, 5, 21, 15, 42, 33, tzinfo=dt_timezone.utc)


class TodayServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        Profile.objects.create(user=cls.user, default_board_thread=cls.daily)
        cls.board = Board.objects.create(thread=cls.daily, state=[])

    def setUp(self):
        # Each test gets a clean board; reload from DB so per-test mutations
        # don't leak via the cached class attribute.
        self.board = Board.objects.get(pk=self.board.pk)
        self.board.state = []
        self.board.save()
        Plan.objects.filter(thread=self.daily).delete()
        Reflection.objects.filter(thread=self.daily).delete()

    # --- text_lines helpers -------------------------------------------------

    def test_text_lines_add_unique(self):
        self.assertEqual(text_lines.add_unique_line(None, "a"), "a")
        self.assertEqual(text_lines.add_unique_line("", "a"), "a")
        self.assertEqual(text_lines.add_unique_line("a", "b"), "a\nb")
        self.assertEqual(text_lines.add_unique_line("a\nb", "a"), "a\nb")

    def test_text_lines_remove(self):
        self.assertEqual(text_lines.remove_line("a\nb\nc", "b"), "a\nc")
        self.assertEqual(text_lines.remove_line("a\nb\na", "a"), "b")
        self.assertEqual(text_lines.remove_line("only", "only"), "")
        self.assertEqual(text_lines.remove_line(None, "x"), "")

    def test_text_lines_normalizes_crlf(self):
        # CRLF-stored fields (e.g. via the CLI's sanitize_string) split into
        # clean lines with no stray \r, and matching ignores the line ending.
        self.assertEqual(text_lines.split_lines("a\r\nb"), ["a", "b"])
        self.assertEqual(text_lines.split_lines("a\rb"), ["a", "b"])
        self.assertTrue(text_lines.has_line("a\r\nb", "a"))
        self.assertEqual(text_lines.remove_line("a\r\nb", "a"), "b")
        self.assertEqual(text_lines.replace_line("a\r\nb", "a", "A"), "A\nb")
        # add_unique_line normalizes the existing field on write.
        self.assertEqual(text_lines.add_unique_line("a\r\nb", "c"), "a\nb\nc")

    # --- board_tree DFS -----------------------------------------------------

    def test_find_task_by_text_walks_children(self):
        deep = create_task_item("deep")
        parent = create_task_item("parent")
        parent["children"] = [deep]
        self.board.state = [create_task_item("top"), parent]
        self.board.save()
        hit = board_tree.find_task_by_text(self.board.state, "deep")
        self.assertIsNotNone(hit)
        _, idx, node = hit
        self.assertEqual(idx, 0)
        self.assertEqual(node["text"], "deep")

    # --- add_task -----------------------------------------------------------

    def test_add_task_appends_to_board_and_plan(self):
        add_task(self.user, "buy bread", today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "buy bread")
        self.assertEqual(self.board.state[0]["data"]["state"], "open")

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "buy bread")

    def test_add_task_is_idempotent(self):
        add_task(self.user, "buy bread", today=TODAY)
        add_task(self.user, "buy bread", today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "buy bread")

    def test_add_task_skips_board_append_when_task_lives_under_children(self):
        parent = create_task_item("parent")
        parent["children"] = [create_task_item("nested")]
        self.board.state = [parent]
        self.board.save()

        add_task(self.user, "nested", today=TODAY)

        self.board.refresh_from_db()
        # Tree shouldn't grow at the root if the task is already nested.
        self.assertEqual(len(self.board.state), 1)
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "nested")

    # --- add_task: carried progress tasks (Copy to today / Move to tomorrow) -

    def test_add_progress_display_form_canonicalises_to_remaining(self):
        # "Copy to today" hands the display form (1/3) back to /add; nothing is
        # done yet, so the whole task (3) is carried onto the new plan.
        add_task(self.user, "New task (1/3)", today=TODAY)

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "New task (3)")

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "New task (3)")

    def test_add_progress_partway_carries_only_remaining(self):
        add_task(self.user, "New task (2/3)", today=TODAY)

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "New task (2)")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["text"], "New task (2)")

    def test_add_progress_renames_existing_board_node_in_place(self):
        # A board node already carries the original total; carrying (2/3)
        # forward rewrites that node's marker to the remaining count, keeping
        # its identity/children rather than appending a duplicate.
        node = create_task_item("New task (3)")
        node["children"] = [create_task_item("subtask")]
        self.board.state = [node]
        self.board.save()

        add_task(self.user, "New task (2/3)", today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "New task (2)")
        self.assertEqual(self.board.state[0]["data"]["text"], "New task (2)")
        # The node kept its subtree — it was renamed, not replaced.
        self.assertEqual(self.board.state[0]["children"][0]["text"], "subtask")

    def test_add_progress_preserves_mid_text_marker_on_board(self):
        self.board.state = [create_task_item("Buy (5) apples")]
        self.board.save()

        add_task(self.user, "Buy (2/5) apples", today=TODAY)

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "Buy (4) apples")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["text"], "Buy (4) apples")

    def test_add_progress_carry_is_idempotent(self):
        add_task(self.user, "New task (2/3)", today=TODAY)
        add_task(self.user, "New task (2/3)", today=TODAY)

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "New task (2)")
        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)

    def test_add_last_step_carries_as_plain_task(self):
        # (3/3) means two of three done -> one remains; the last item drops the
        # counter and carries forward as a plain task.
        self.board.state = [create_task_item("New task (3)")]
        self.board.save()

        add_task(self.user, "New task (3/3)", today=TODAY)

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "New task")
        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "New task")
        self.assertEqual(self.board.state[0]["data"]["text"], "New task")

    def test_copy_finished_task_carries_as_plain_task(self):
        # A finished counted task on another day (display capped at (K/K));
        # "Copy to today" drops the counter entirely rather than leaving a "(1)".
        YESTERDAY = date_cls(2026, 5, 20)
        add_task(self.user, "New task (2)", today=YESTERDAY)
        set_task_done(self.user, "New task (2)", True, today=YESTERDAY)
        set_task_done(self.user, "New task (1/2)", True, today=YESTERDAY)  # (2/2)

        add_task(self.user, "New task (2/2)", today=TODAY)

        today_plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(today_plan.focus, "New task")
        # Yesterday's counted line is untouched; the shared board node is stripped.
        yesterday_plan = Plan.objects.get(pub_date=YESTERDAY, thread=self.daily)
        self.assertEqual(yesterday_plan.focus, "New task (2)")
        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "New task")

    def test_move_last_step_to_tomorrow_as_plain_task(self):
        TOMORROW = date_cls(2026, 5, 22)
        add_task(self.user, "New task (2)", today=TODAY)
        set_task_done(self.user, "New task (2)", True, today=TODAY)  # display (2/2)

        add_task(self.user, "New task (2/2)", today=TOMORROW)
        delete_task(self.user, "New task (2/2)", today=TODAY)

        tomorrow_plan = Plan.objects.get(pub_date=TOMORROW, thread=self.daily)
        self.assertEqual(tomorrow_plan.focus, "New task")
        today_plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(today_plan.focus, "")
        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "New task")

    def test_move_progress_task_to_tomorrow(self):
        # Full "Move to tomorrow": the task was added and one step ticked, so
        # today's list shows it as (2/3). Moving hands that display form to
        # /add (for tomorrow) then /delete (for today).
        TOMORROW = date_cls(2026, 5, 22)
        add_task(self.user, "New task (3)", today=TODAY)
        set_task_done(self.user, "New task (3)", True, today=TODAY)

        add_task(self.user, "New task (2/3)", today=TOMORROW)
        delete_task(self.user, "New task (2/3)", today=TODAY)

        # Tomorrow carries the two remaining steps; today's plan line is gone.
        tomorrow_plan = Plan.objects.get(pub_date=TOMORROW, thread=self.daily)
        self.assertEqual(tomorrow_plan.focus, "New task (2)")
        today_plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(today_plan.focus, "")

        # The single shared board node now reflects the remaining count and is
        # still present (it's the carried work, not a deletion).
        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "New task (2)")

        # Today keeps its record of the step done that day.
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "New task (1)")

    # --- set_task_done ------------------------------------------------------

    def test_set_task_done_true_marks_board_and_appends_reflection(self):
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["data"]["state"], "done")
        # The Vue Board view renders a node as checked from this flag.
        self.assertTrue(self.board.state[0]["state"]["checked"])

        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

    def test_set_task_done_false_clears_board_checked_flag(self):
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)
        set_task_done(self.user, "buy bread", False, today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["data"]["state"], "open")
        self.assertFalse(self.board.state[0]["state"]["checked"])

    def test_set_task_done_false_removes_only_that_reflection_line(self):
        add_task(self.user, "buy bread", today=TODAY)
        add_task(self.user, "walk dog", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)
        set_task_done(self.user, "walk dog", True, today=TODAY)

        set_task_done(self.user, "buy bread", False, today=TODAY)

        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "walk dog")

        self.board.refresh_from_db()
        states = {n["text"]: n["data"]["state"] for n in self.board.state}
        self.assertEqual(states["buy bread"], "open")
        self.assertEqual(states["walk dog"], "done")

    def test_set_task_done_on_unknown_task_appends_it(self):
        set_task_done(self.user, "surprise", True, today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "surprise")
        self.assertEqual(self.board.state[0]["data"]["state"], "done")
        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "surprise")

    # --- delete_task --------------------------------------------------------

    def test_delete_task_removes_leaf_from_board_and_plan(self):
        add_task(self.user, "buy bread", today=TODAY)
        delete_task(self.user, "buy bread", today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "")

    def test_delete_task_keeps_node_with_children_on_board(self):
        parent = create_task_item("parent")
        parent["children"] = [create_task_item("kid")]
        self.board.state = [parent]
        self.board.save()
        Plan.objects.create(pub_date=TODAY, thread=self.daily, focus="parent")

        delete_task(self.user, "parent", today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "parent")

        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(plan.focus, "")

    def test_delete_task_leaves_reflection_good_untouched(self):
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)

        delete_task(self.user, "buy bread", today=TODAY)

        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

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

    def test_add_task_rolls_back_board_on_plan_save_failure(self):
        with mock.patch(
            "tasks.apps.tree.services.today.operations.Plan.objects.get_or_create",
            side_effect=DatabaseError("boom"),
        ):
            with self.assertRaises(DatabaseError):
                add_task(self.user, "explode", today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])
        self.assertFalse(Plan.objects.filter(pub_date=TODAY).exists())

    def test_no_board_raises_nobooarderror(self):
        Board.objects.all().delete()
        with self.assertRaises(NoBoardError):
            add_task(self.user, "x", today=TODAY)

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

    def test_journal_failure_rolls_back_reflection_and_board(self):
        add_task(self.user, "buy bread", today=TODAY)

        with mock.patch(
            "tasks.apps.tree.services.today.operations.JournalAdded.objects.create",
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

        # Reflection.good must NOT contain the line; board node must still
        # be open.
        self.assertFalse(JournalAdded.objects.exists())
        reflection = Reflection.objects.filter(thread=self.daily).first()
        self.assertTrue(reflection is None or reflection.good == "")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["data"]["state"], "open")
