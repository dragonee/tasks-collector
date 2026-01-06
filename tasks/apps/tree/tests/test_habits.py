from django.test import TestCase

from ..models import Habit, HabitKeyword
from ..services.journalling.habit_extraction import habits_line_to_habits_tracked


class HabitParsingTestCase(TestCase):
    """Test cases for habit parsing functionality."""

    def setUp(self):
        """Set up test habits with keywords."""
        # Create a habit with single keyword
        self.food_habit = Habit.objects.create(
            name="Food",
            slug="food",
        )
        HabitKeyword.objects.create(habit=self.food_habit, keyword="food")

        # Create a habit with multiple keywords
        self.workout_habit = Habit.objects.create(
            name="Workout",
            slug="workout",
        )
        HabitKeyword.objects.create(habit=self.workout_habit, keyword="workout")
        HabitKeyword.objects.create(habit=self.workout_habit, keyword="siłka")

        # Create another habit
        self.meditation_habit = Habit.objects.create(
            name="Meditation",
            slug="meditation",
        )
        HabitKeyword.objects.create(habit=self.meditation_habit, keyword="medytacja")

    def _parse_and_check(self, line, expected_result):
        """Run habits_line_to_habits_tracked and assert the result matches the expected result."""

        result = habits_line_to_habits_tracked(line)

        self.assertEqual(len(result), len(expected_result))

        for i in range(len(result)):
            occured, habit, note = result[i]
            expected_occured, expected_habit, expected_note = expected_result[i]
            self.assertEqual(occured, expected_occured)
            self.assertEqual(habit, expected_habit)
            self.assertEqual(note, expected_note)

    def test_a_single_habit_tracked_can_be_parsed(self):
        """A single tracked habit (#) can be parsed."""
        self._parse_and_check(
            "#food pizza",
            [
                (True, self.food_habit, "#food pizza"),
            ],
        )

    def test_a_single_skipped_habit_can_be_parsed(self):
        """A single skipped habit (!) can be parsed."""
        self._parse_and_check(
            "!food nie dzisiaj", [(False, self.food_habit, "!food nie dzisiaj")]
        )

    def test_multiple_habits_can_be_separated_by_space(self):
        """Multiple habits can be separated by space."""
        self._parse_and_check(
            "#food kebab #workout trening",
            [
                (True, self.food_habit, "#food kebab"),
                (True, self.workout_habit, "#workout trening"),
            ],
        )

    def test_multiple_habits_can_be_separated_by_new_line(self):
        """Multiple habits can also be separated by new line."""
        self._parse_and_check(
            "#food kebab\n#workout trening",
            [
                (True, self.food_habit, "#food kebab"),
                (True, self.workout_habit, "#workout trening"),
            ],
        )

    def test_multiple_habits_can_mix_tracked_and_skipped_markers(self):
        """Multiple habits can mix tracked and skipped markers."""
        self._parse_and_check(
            "#food pizza !medytacja niestety",
            [
                (True, self.food_habit, "#food pizza"),
                (False, self.meditation_habit, "!medytacja niestety"),
            ],
        )

    def test_a_habit_can_be_referenced_by_alternative_keyword(self):
        """A habit can be referenced by alternative keyword."""
        # Use 'siłka' keyword which maps to workout habit
        self._parse_and_check(
            "#siłka dzisiaj", [(True, self.workout_habit, "#siłka dzisiaj")]
        )

    def test_non_existent_keywords_are_ignored(self):
        """Non-existent keywords are ignored."""
        self._parse_and_check("#nonexistent test", [])

    def test_empty_line_does_not_raise_any_errors(self):
        """An empty line does not raise any errors."""
        self._parse_and_check("", [])

    def test_a_line_without_habit_markers_is_ignored(self):
        """A line without # or ! markers is ignored."""
        self._parse_and_check("just some text", [])

    def test_unicode_strings_are_supported(self):
        """Unicode strings are supported."""
        self._parse_and_check(
            "#medytacja dziś rano",
            [(True, self.meditation_habit, "#medytacja dziś rano")],
        )
