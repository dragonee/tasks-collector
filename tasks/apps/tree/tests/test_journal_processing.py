from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ..board_operations import create_task_item
from ..models import (
    Board,
    Habit,
    HabitKeyword,
    HabitTracked,
    JournalAdded,
    Profile,
    Reflection,
    Thread,
)
from ..services.journalling.journal_processing import process_journal_entry


class JournalProcessingTestCase(TestCase):
    """Test cases for journal entry processing."""

    def setUp(self):
        """Set up test fixtures."""
        self.daily_thread = Thread.objects.create(name="Daily")
        self.weekly_thread = Thread.objects.create(name="Weekly")

        self.food_habit = Habit.objects.create(name="Food", slug="food")
        HabitKeyword.objects.create(habit=self.food_habit, keyword="food")

    def _create_journal(self, comment, thread=None):
        """Helper to create a JournalAdded instance."""
        if thread is None:
            thread = self.daily_thread
        return JournalAdded.objects.create(
            comment=comment,
            thread=thread,
            published=timezone.now(),
        )

    def test_entry_without_reflection_items_does_not_create_reflection(self):
        """An entry without reflection markers does not create a Reflection."""
        journal = self._create_journal("Just a regular journal entry")

        process_journal_entry(journal)

        self.assertEqual(Reflection.objects.count(), 0)

    def test_entry_with_good_reflection_item_updates_good_field(self):
        """An entry with [x] marker updates the good field."""
        journal = self._create_journal("[x] completed a task")

        process_journal_entry(journal)

        reflection = Reflection.objects.get()
        self.assertEqual(reflection.good, "completed a task")
        self.assertFalse(reflection.better)
        self.assertFalse(reflection.best)

    def test_entry_with_better_reflection_item_updates_better_field(self):
        """An entry with [~] marker updates the better field."""
        journal = self._create_journal("[~] could have started earlier")

        process_journal_entry(journal)

        reflection = Reflection.objects.get()
        self.assertFalse(reflection.good)
        self.assertEqual(reflection.better, "could have started earlier")
        self.assertFalse(reflection.best)

    def test_entry_with_best_reflection_item_updates_best_field(self):
        """An entry with [^] marker updates the best field."""
        journal = self._create_journal("[^] wake up at 6am every day")

        process_journal_entry(journal)

        reflection = Reflection.objects.get()
        self.assertFalse(reflection.good)
        self.assertFalse(reflection.better)
        self.assertEqual(reflection.best, "wake up at 6am every day")

    def test_entry_with_all_reflection_types_updates_all_fields(self):
        """An entry with [x], [~], and [^] markers updates all fields."""
        journal = self._create_journal(
            "[x] finished the report\n[~] should have proofread\n[^] become a better writer"
        )

        process_journal_entry(journal)

        reflection = Reflection.objects.get()
        self.assertEqual(reflection.good, "finished the report")
        self.assertEqual(reflection.better, "should have proofread")
        self.assertEqual(reflection.best, "become a better writer")

    def test_reflection_items_are_appended_not_replaced(self):
        """Subsequent entries append to existing reflection, not replace."""
        journal1 = self._create_journal("[x] first good thing")
        process_journal_entry(journal1)

        journal2 = self._create_journal("[x] second good thing")
        process_journal_entry(journal2)

        reflection = Reflection.objects.get()
        self.assertEqual(reflection.good, "first good thing\nsecond good thing")

    def test_reflection_items_are_deduplicated(self):
        """The same [x] line from two entries is stored once (dedup)."""
        process_journal_entry(self._create_journal("[x] same good thing"))
        process_journal_entry(self._create_journal("[x] same good thing"))

        reflection = Reflection.objects.get()
        self.assertEqual(reflection.good, "same good thing")

    def test_leading_list_bullet_is_stripped(self):
        """A markdown list bullet before the marker is stripped from the
        stored line, so ``- [x] foo`` yields ``foo`` (not ``- foo``)."""
        process_journal_entry(self._create_journal("- [x] did a thing"))

        reflection = Reflection.objects.get()
        self.assertEqual(reflection.good, "did a thing")

    def test_entry_with_valid_habit_creates_habit_tracked(self):
        """An entry with a valid #habit creates a HabitTracked entry."""
        journal = self._create_journal("#food pizza for lunch")

        process_journal_entry(journal)

        self.assertEqual(HabitTracked.objects.count(), 1)
        habit_tracked = HabitTracked.objects.get()
        self.assertEqual(habit_tracked.habit, self.food_habit)
        self.assertTrue(habit_tracked.occured)
        self.assertEqual(habit_tracked.note, "#food pizza for lunch")
        self.assertEqual(habit_tracked.thread, self.daily_thread)

    def test_entry_with_invalid_habit_fails_silently(self):
        """An entry with an invalid #habit does not raise an error."""
        journal = self._create_journal("#nonexistent some text")

        # Should not raise any exception
        process_journal_entry(journal)

        self.assertEqual(HabitTracked.objects.count(), 0)

    def test_skip_habits_flag_prevents_habit_tracking(self):
        """When skip_habits=True, no HabitTracked entries are created."""
        journal = self._create_journal("#food pizza for lunch")

        process_journal_entry(journal, skip_habits=True)

        self.assertEqual(HabitTracked.objects.count(), 0)

    def test_skip_habits_flag_still_processes_reflections(self):
        """When skip_habits=True, reflections are still processed."""
        journal = self._create_journal("[x] good thing\n#food pizza")

        process_journal_entry(journal, skip_habits=True)

        self.assertEqual(HabitTracked.objects.count(), 0)
        reflection = Reflection.objects.get()
        self.assertEqual(reflection.good, "good thing")

    def test_quoted_lines_are_ignored(self):
        """Lines starting with `>` are treated as blockquotes and skipped."""
        journal = self._create_journal(
            "> - [x] quoted reflection\n"
            "> #food quoted habit\n"
            "[x] real reflection\n"
            "#food real habit"
        )

        process_journal_entry(journal)

        reflection = Reflection.objects.get()
        self.assertEqual(reflection.good, "real reflection")
        self.assertEqual(HabitTracked.objects.count(), 1)
        self.assertEqual(HabitTracked.objects.get().note, "#food real habit")

    def test_indented_and_nested_quoted_lines_are_ignored(self):
        """Indented (`  >`) and nested (`>>`) quote lines are also skipped."""
        journal = self._create_journal(
            "  > [x] indented quote\n" ">> #food nested quote\n" "[x] kept"
        )

        process_journal_entry(journal)

        reflection = Reflection.objects.get()
        self.assertEqual(reflection.good, "kept")
        self.assertEqual(HabitTracked.objects.count(), 0)

    def test_mid_line_gt_is_not_treated_as_quote(self):
        """A `>` that is not at the line start does not skip the line."""
        journal = self._create_journal("#food eaten > a lot")

        process_journal_entry(journal)

        self.assertEqual(HabitTracked.objects.count(), 1)
        self.assertEqual(HabitTracked.objects.get().note, "#food eaten > a lot")


class JournalBoardCheckTestCase(TestCase):
    """process_journal_entry(user=...) ticks matching current-board tasks."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="phone", password="x")
        self.daily = Thread.objects.create(name="Daily")
        Profile.objects.create(user=self.user, default_board_thread=self.daily)
        self.board = Board.objects.create(thread=self.daily, state=[])

    def _add_board_task(self, text):
        self.board.state.append(create_task_item(text))
        self.board.save()

    def _journal(self, comment):
        return JournalAdded.objects.create(
            comment=comment, thread=self.daily, published=timezone.now()
        )

    def _board_node(self, text):
        self.board.refresh_from_db()
        for node in self.board.state:
            if node["data"]["text"] == text:
                return node
        return None

    def test_matching_boolean_task_is_checked_and_reflection_deduped(self):
        self._add_board_task("buy bread")

        process_journal_entry(self._journal("[x] buy bread"), user=self.user)

        self.assertEqual(self._board_node("buy bread")["data"]["state"], "done")
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")

    def test_matching_progress_task_is_advanced(self):
        self._add_board_task("Do tasks (2/3)")

        process_journal_entry(self._journal("[x] Do tasks (2/3)"), user=self.user)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["data"]["text"], "Do tasks (3/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "done")
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "Do tasks (3/3)")

    def test_unmatched_line_creates_no_board_task(self):
        process_journal_entry(self._journal("[x] not on the board"), user=self.user)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "not on the board")

    def test_without_user_board_is_untouched(self):
        self._add_board_task("buy bread")

        process_journal_entry(self._journal("[x] buy bread"))

        self.assertEqual(self._board_node("buy bread")["data"]["state"], "open")

    def test_bullet_prefixed_line_matches_and_advances_progress_task(self):
        # ``- [x] <task>`` (markdown-checkbox style) must strip the leading
        # bullet so it matches the board task text and progresses it.
        self._add_board_task("Pyszne posiłki (3)")

        process_journal_entry(self._journal("- [x] Pyszne posiłki (3)"), user=self.user)

        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["data"]["text"], "Pyszne posiłki (1/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "open")
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "Pyszne posiłki (3)")
