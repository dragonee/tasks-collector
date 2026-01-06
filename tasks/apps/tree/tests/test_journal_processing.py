from django.test import TestCase
from django.utils import timezone

from ..models import Habit, HabitKeyword, HabitTracked, JournalAdded, Reflection, Thread
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
