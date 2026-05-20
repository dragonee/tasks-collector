from datetime import date as date_cls
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase

from ..models import Board, Plan, Profile, Reflection, Thread
from ..services.today import board_tree, set_task_done, text_lines
from ..services.today.progress import parse_progress, render_progress

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

    def test_clamps_current_above_total(self):
        p = parse_progress("(7/4) overshoot")
        self.assertEqual((p.current, p.total), (4, 4))


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
        """Put text into Plan and on the board at root level."""
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

    # --- forward progression -----------------------------------------------

    def test_first_tick_promotes_pristine_to_partial(self):
        self._seed("Do tasks (3)")

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Do tasks (1/3)")
        self.assertEqual(self.board.state[0]["text"], "Do tasks (1/3)")
        self.assertEqual(self.board.state[0]["data"]["text"], "Do tasks (1/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "open")
        # Reflection.good must NOT contain the partial form.
        self.assertTrue(reflection is None or "Do tasks" not in (reflection.good or ""))

    def test_tick_partial_to_partial(self):
        self._seed("Do tasks (1/3)")

        set_task_done(self.user, "Do tasks (1/3)", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Do tasks (2/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "open")
        self.assertTrue(reflection is None or "Do tasks" not in (reflection.good or ""))

    def test_final_tick_marks_complete_and_adds_to_reflection(self):
        self._seed("Do tasks (2/3)")

        set_task_done(self.user, "Do tasks (2/3)", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Do tasks (3/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "done")
        self.assertEqual(reflection.good, "Do tasks (3/3)")

    def test_full_cycle_3_to_complete(self):
        self._seed("Do tasks (3)")

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)
        plan, _ = self._reload()
        self.assertEqual(plan.focus, "Do tasks (1/3)")

        set_task_done(self.user, "Do tasks (1/3)", True, today=TODAY)
        plan, _ = self._reload()
        self.assertEqual(plan.focus, "Do tasks (2/3)")

        set_task_done(self.user, "Do tasks (2/3)", True, today=TODAY)
        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Do tasks (3/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "done")
        self.assertEqual(reflection.good, "Do tasks (3/3)")

    def test_single_step_task_completes_on_first_tick(self):
        self._seed("Quick (1)")

        set_task_done(self.user, "Quick (1)", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Quick (1/1)")
        self.assertEqual(self.board.state[0]["data"]["state"], "done")
        self.assertEqual(reflection.good, "Quick (1/1)")

    # --- no-ops ------------------------------------------------------------

    def test_tick_on_complete_is_noop(self):
        self._seed("Done (3/3)")
        Reflection.objects.create(pub_date=TODAY, thread=self.daily, good="Done (3/3)")
        self.board.state[0]["data"]["state"] = "done"
        self.board.save()

        set_task_done(self.user, "Done (3/3)", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Done (3/3)")
        self.assertEqual(reflection.good, "Done (3/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "done")

    def test_untick_on_pristine_is_noop(self):
        self._seed("Fresh (3)")

        set_task_done(self.user, "Fresh (3)", False, today=TODAY)

        plan, _reflection = self._reload()
        self.assertEqual(plan.focus, "Fresh (3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "open")

    def test_untick_on_partial_is_noop(self):
        self._seed("Mid (2/3)")

        set_task_done(self.user, "Mid (2/3)", False, today=TODAY)

        plan, _reflection = self._reload()
        self.assertEqual(plan.focus, "Mid (2/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "open")

    # --- backward (only from full) ----------------------------------------

    def test_untick_from_complete_resets_to_pristine(self):
        self._seed("Done (3/3)")
        Reflection.objects.create(pub_date=TODAY, thread=self.daily, good="Done (3/3)")
        self.board.state[0]["data"]["state"] = "done"
        self.board.save()

        set_task_done(self.user, "Done (3/3)", False, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Done (3)")
        self.assertEqual(self.board.state[0]["text"], "Done (3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "open")
        self.assertEqual(reflection.good, "")

    # --- marker placement variations --------------------------------------

    def test_mid_text_marker(self):
        self._seed("Buy (5) apples")

        set_task_done(self.user, "Buy (5) apples", True, today=TODAY)

        plan, _ = self._reload()
        self.assertEqual(plan.focus, "Buy (1/5) apples")
        self.assertEqual(self.board.state[0]["text"], "Buy (1/5) apples")

    def test_leading_marker(self):
        self._seed("(2/4) Walk 1km")

        set_task_done(self.user, "(2/4) Walk 1km", True, today=TODAY)

        plan, _ = self._reload()
        self.assertEqual(plan.focus, "(3/4) Walk 1km")

    # --- fallthrough to boolean -------------------------------------------

    def test_plain_task_still_uses_boolean_path(self):
        self._seed("pay bills")

        set_task_done(self.user, "pay bills", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "pay bills")  # text unchanged
        self.assertEqual(self.board.state[0]["data"]["state"], "done")
        self.assertEqual(reflection.good, "pay bills")

    # --- co-existence with other tasks ------------------------------------

    def test_only_target_line_in_plan_renames(self):
        Plan.objects.create(
            pub_date=TODAY, thread=self.daily, focus="Do tasks (3)\nother task"
        )
        self.board.state = [
            board_tree.append_task_at_root([], "Do tasks (3)"),
        ]
        self.board.save()

        set_task_done(self.user, "Do tasks (3)", True, today=TODAY)

        plan, _ = self._reload()
        self.assertEqual(plan.focus, "Do tasks (1/3)\nother task")

    # --- atomicity --------------------------------------------------------

    def test_reflection_failure_rolls_back_board_and_plan(self):
        self._seed("Done (2/3)")

        with mock.patch(
            "tasks.apps.tree.services.today.operations.Reflection.save",
            side_effect=DatabaseError("boom"),
        ):
            with self.assertRaises(DatabaseError):
                set_task_done(self.user, "Done (2/3)", True, today=TODAY)

        plan, reflection = self._reload()
        self.assertEqual(plan.focus, "Done (2/3)")
        self.assertEqual(self.board.state[0]["text"], "Done (2/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "open")
        self.assertIsNone(reflection)
