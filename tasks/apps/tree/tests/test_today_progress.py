from datetime import date as date_cls
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase

from ..models import Board, Plan, Profile, Reflection, Thread
from ..services.today import board_tree, plan_tasks, set_task_done, text_lines
from ..services.today.progress import (
    parse_progress,
    remaining_after,
    render_carried,
    render_progress,
)

TODAY = date_cls(2026, 5, 21)


class ProgressParseTestCase(TestCase):
    def test_parses_marker_at_end(self):
        p = parse_progress("Do tasks (3)")
        self.assertEqual((p.current, p.total), (0, 3))
        self.assertEqual(p.span, (9, 12))

    def test_parses_marker_in_middle(self):
        p = parse_progress("Buy (5) apples")
        self.assertEqual((p.current, p.total), (0, 5))

    def test_parses_progress_at_start(self):
        p = parse_progress("(2/4) Walk 1km")
        self.assertEqual((p.current, p.total), (2, 4))

    def test_first_marker_wins(self):
        p = parse_progress("Do (1/3) the (5) thing")
        self.assertEqual((p.current, p.total), (1, 3))

    def test_rejects_total_zero(self):
        self.assertIsNone(parse_progress("Tasks (0)"))
        self.assertIsNone(parse_progress("Tasks (0/0)"))
        self.assertIsNone(parse_progress("Tasks (3/0)"))

    def test_returns_none_when_no_marker(self):
        self.assertIsNone(parse_progress("pay bills"))
        self.assertIsNone(parse_progress(""))
        self.assertIsNone(parse_progress(None))

    def test_ignores_non_digit_parens(self):
        self.assertIsNone(parse_progress("(foo) (bar)"))
        self.assertIsNone(parse_progress("Hello (world)"))

    def test_preserves_overshoot(self):
        # Over-quota states like (7/4) are now legitimate — they're how
        # "Add another" tracks repeated completions past the plan.
        p = parse_progress("(7/4) overshoot")
        self.assertEqual((p.current, p.total), (7, 4))


class ProgressRenderTestCase(TestCase):
    def test_pristine_form(self):
        p = parse_progress("Do tasks (1/3)")
        self.assertEqual(render_progress("Do tasks (1/3)", p, 0), "Do tasks (3)")

    def test_increment_to_partial(self):
        p = parse_progress("Do tasks (3)")
        self.assertEqual(render_progress("Do tasks (3)", p, 1), "Do tasks (1/3)")

    def test_increment_to_complete(self):
        p = parse_progress("Do tasks (2/3)")
        self.assertEqual(render_progress("Do tasks (2/3)", p, 3), "Do tasks (3/3)")

    def test_preserves_surrounding_text(self):
        p = parse_progress("Buy (5) apples and bread")
        self.assertEqual(
            render_progress("Buy (5) apples and bread", p, 1),
            "Buy (1/5) apples and bread",
        )

    def test_preserves_leading_marker(self):
        p = parse_progress("(2/4) Walk 1km")
        self.assertEqual(
            render_progress("(2/4) Walk 1km", p, 3),
            "(3/4) Walk 1km",
        )


class RemainingAfterTestCase(TestCase):
    def test_nothing_done_carries_full_total(self):
        # (1/3) means nothing done yet -> all 3 remain.
        self.assertEqual(remaining_after("New task (1/3)"), 3)

    def test_partway_carries_remaining(self):
        # (2/3) means one done -> two remain.
        self.assertEqual(remaining_after("New task (2/3)"), 2)

    def test_last_step_carries_one(self):
        # (3/3) means two done -> one remains.
        self.assertEqual(remaining_after("New task (3/3)"), 1)

    def test_bare_count_is_already_canonical(self):
        # A single-number (K) form is the stored/canonical shape already.
        self.assertIsNone(remaining_after("New task (3)"))

    def test_no_marker(self):
        self.assertIsNone(remaining_after("pay bills"))
        self.assertIsNone(remaining_after(""))
        self.assertIsNone(remaining_after(None))

    def test_overshoot_leaves_nothing_to_carry(self):
        # Over-quota display never reaches the client (it caps at (K/K)), but
        # a hand-typed (4/3) has -1 remaining -> nothing to carry.
        self.assertIsNone(remaining_after("New task (4/3)"))

    def test_uses_first_marker(self):
        self.assertEqual(remaining_after("Do (2/3) the (5) thing"), 2)


class RenderCarriedTestCase(TestCase):
    def test_multiple_remaining_keeps_counter(self):
        self.assertEqual(render_carried("New task (2/3)", 2), "New task (2)")

    def test_one_remaining_drops_marker(self):
        # Last item / finished task -> plain, counter-less task.
        self.assertEqual(render_carried("New task (3/3)", 1), "New task")

    def test_one_remaining_drops_mid_text_marker(self):
        self.assertEqual(render_carried("Buy (2/2) apples", 1), "Buy apples")

    def test_no_marker_unchanged(self):
        self.assertEqual(render_carried("pay bills", 1), "pay bills")


class ReplaceLineTestCase(TestCase):
    def test_replaces_only_matching_line(self):
        self.assertEqual(
            text_lines.replace_line("a\nb\nc", "b", "B"),
            "a\nB\nc",
        )

    def test_returns_value_when_old_absent(self):
        self.assertEqual(text_lines.replace_line("a\nb", "x", "X"), "a\nb")

    def test_handles_empty(self):
        self.assertEqual(text_lines.replace_line("", "a", "b"), "")
        self.assertEqual(text_lines.replace_line(None, "a", "b"), "")

    def test_replaces_all_occurrences(self):
        self.assertEqual(
            text_lines.replace_line("a\nb\na", "a", "A"),
            "A\nb\nA",
        )


class ProgressLifecycleTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        Profile.objects.create(user=cls.user, default_board_thread=cls.daily)
        cls.board = Board.objects.create(thread=cls.daily, state=[])

    def setUp(self):
        self.board = Board.objects.get(pk=self.board.pk)
        self.board.state = []
        self.board.save()
        Plan.objects.filter(thread=self.daily).delete()
        Reflection.objects.filter(thread=self.daily).delete()

    def _seed(self, text):
        """Put the total-form task into Plan and on the board at root level.
        Under the reflection-count model this text is never rewritten."""
        Plan.objects.create(pub_date=TODAY, thread=self.daily, focus=text)
        self.board.state = [board_tree.append_task_at_root([], text)]
        self.board.save()

    def _reload(self):
        self.board.refresh_from_db()
        plan = Plan.objects.get(pub_date=TODAY, thread=self.daily)
        reflection = Reflection.objects.filter(
            pub_date=TODAY, thread=self.daily
        ).first()
        return plan, reflection

    def _node(self):
        self.board.refresh_from_db()
        return self.board.state[0]

    def _display(self):
        return [(t.text, t.done) for t in plan_tasks(TODAY, "Daily")]

    # --- forward progression: Plan/Board text fixed, count logged ----------

    def test_first_tick_logs_count_and_derives_partial(self):
        self._seed("Do tasks (3)")

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)

        plan, reflection = self._reload()
        # Plan and Board text are never rewritten.
        self.assertEqual(plan.focus, "Do tasks (3)")
        self.assertEqual(self._node()["data"]["text"], "Do tasks (3)")
        self.assertEqual(self._node()["data"]["state"], "open")  # 1 < 3
        # The count is logged in the Reflection.
        self.assertEqual(reflection.good, "Do tasks (1)")
        # Display derives (2/3) from N=1.
        self.assertEqual(self._display(), [("Do tasks (2/3)", False)])

    def test_full_cycle_accumulates_counts_and_crosses_at_total(self):
        self._seed("Do tasks (3)")

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)
        self.assertEqual(self._display(), [("Do tasks (2/3)", False)])

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)
        self.assertEqual(self._display(), [("Do tasks (3/3)", False)])

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)
        plan, reflection = self._reload()
        self.assertEqual(reflection.good, "Do tasks (1)\nDo tasks (2)\nDo tasks (3)")
        self.assertEqual(plan.focus, "Do tasks (3)")  # unchanged
        self.assertEqual(self._node()["data"]["state"], "done")  # crossed at N>=3
        self.assertTrue(self._node()["state"]["checked"])
        self.assertEqual(self._display(), [("Do tasks (3/3)", True)])

    def test_single_step_task_completes_on_first_tick(self):
        self._seed("Quick (1)")

        set_task_done(self.user, "Quick (1)", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(reflection.good, "Quick (1)")
        self.assertEqual(self._node()["data"]["state"], "done")  # 1 >= 1
        self.assertEqual(self._display(), [("Quick (1/1)", True)])

    # --- "Add another" past full: over-quota counts, stays crossed --------

    def test_add_another_past_full_keeps_advancing_and_crossed(self):
        self._seed("Do tasks (3)")
        for _ in range(3):
            set_task_done(self.user, "Do tasks (3)", True, today=TODAY)
        self.assertEqual(self._node()["data"]["state"], "done")

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)  # 4th

        _plan, reflection = self._reload()
        self.assertIn("Do tasks (4)", reflection.good)
        self.assertEqual(self._node()["data"]["state"], "done")  # 4 >= 3
        self.assertEqual(self._display(), [("Do tasks (3/3)", True)])  # step capped

    # --- untick: decrement the count, un-cross ----------------------------

    def test_untick_from_complete_decrements_and_uncrosses(self):
        self._seed("Do tasks (3)")
        for _ in range(3):
            set_task_done(self.user, "Do tasks (3)", True, today=TODAY)
        self.assertEqual(self._node()["data"]["state"], "done")

        set_task_done(self.user, "Do tasks (3)", False, today=TODAY)

        _plan, reflection = self._reload()
        self.assertEqual(reflection.good, "Do tasks (1)\nDo tasks (2)")  # (3) removed
        self.assertEqual(self._node()["data"]["state"], "open")  # 2 < 3
        self.assertEqual(self._display(), [("Do tasks (3/3)", False)])  # N=2 -> step 3

    def test_untick_at_zero_is_noop(self):
        self._seed("Fresh (3)")

        result = set_task_done(self.user, "Fresh (3)", False, today=TODAY)

        self.assertIsNone(result)
        _plan, reflection = self._reload()
        self.assertEqual(self._node()["data"]["state"], "open")
        self.assertTrue(reflection is None or not reflection.good)

    def test_untick_on_partial_decrements(self):
        self._seed("Mid (3)")
        set_task_done(self.user, "Mid (3)", True, today=TODAY)  # N=1

        set_task_done(self.user, "Mid (3)", False, today=TODAY)  # back to 0

        _plan, reflection = self._reload()
        self.assertEqual(reflection.good, "")
        self.assertEqual(self._node()["data"]["state"], "open")

    # --- marker placement variations --------------------------------------

    def test_mid_text_marker_logs_count_base(self):
        self._seed("Buy (5) apples")

        set_task_done(self.user, "Buy (5) apples", True, today=TODAY)

        _plan, reflection = self._reload()
        self.assertEqual(reflection.good, "Buy (1) apples")
        self.assertEqual(self._display(), [("Buy (2/5) apples", False)])

    def test_leading_marker_logs_count_base(self):
        self._seed("(4) Walk 1km")

        set_task_done(self.user, "(4) Walk 1km", True, today=TODAY)

        _plan, reflection = self._reload()
        self.assertEqual(reflection.good, "(1) Walk 1km")
        self.assertEqual(self._display(), [("(2/4) Walk 1km", False)])

    # --- fallthrough to boolean -------------------------------------------

    def test_plain_task_still_uses_boolean_path(self):
        self._seed("pay bills")

        set_task_done(self.user, "pay bills", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "pay bills")  # text unchanged
        self.assertEqual(self._node()["data"]["state"], "done")
        self.assertEqual(reflection.good, "pay bills")

    # --- co-existence with other tasks ------------------------------------

    def test_only_target_task_progresses(self):
        Plan.objects.create(
            pub_date=TODAY, thread=self.daily, focus="Do tasks (3)\nother task"
        )
        self.board.state = [board_tree.append_task_at_root([], "Do tasks (3)")]
        self.board.save()

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Do tasks (3)\nother task")  # unchanged
        self.assertEqual(reflection.good, "Do tasks (1)")
        self.assertEqual(
            self._display(),
            [("Do tasks (2/3)", False), ("other task", False)],
        )

    # --- atomicity --------------------------------------------------------

    def test_reflection_failure_rolls_back_board(self):
        self._seed("Do tasks (3)")

        with mock.patch(
            "tasks.apps.tree.services.today.operations.Reflection.save",
            side_effect=DatabaseError("boom"),
        ):
            with self.assertRaises(DatabaseError):
                set_task_done(self.user, "Do tasks (3)", True, today=TODAY)

        _plan, reflection = self._reload()
        self.assertEqual(self._node()["data"]["state"], "open")
        self.assertTrue(reflection is None or not reflection.good)
