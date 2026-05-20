from datetime import date as date_cls
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase

from ..board_operations import create_task_item
from ..models import Board, Plan, Profile, Reflection, Thread
from ..services.today import (
    NoBoardError,
    add_task,
    board_tree,
    delete_task,
    list_today_tasks,
    set_task_done,
    text_lines,
)

TODAY = date_cls(2026, 5, 21)


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

    # --- set_task_done ------------------------------------------------------

    def test_set_task_done_true_marks_board_and_appends_reflection(self):
        add_task(self.user, "buy bread", today=TODAY)
        set_task_done(self.user, "buy bread", True, today=TODAY)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["data"]["state"], "done")

        reflection = Reflection.objects.get(pub_date=TODAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

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
