from django.test import TestCase
from ..habits import habits_line_to_habits_tracked
from ..models import Habit, HabitKeyword


class HabitParsingTestCase(TestCase):
    """Test cases for habit parsing functionality."""

    def setUp(self):
        """Set up test habits with keywords."""
        # Create a habit with single keyword
        self.food_habit = Habit.objects.create(
            name='Food',
            slug='food',
        )
        HabitKeyword.objects.create(habit=self.food_habit, keyword='food')

        # Create a habit with multiple keywords
        self.workout_habit = Habit.objects.create(
            name='Workout',
            slug='workout',
        )
        HabitKeyword.objects.create(habit=self.workout_habit, keyword='workout')
        HabitKeyword.objects.create(habit=self.workout_habit, keyword='siłka')

        # Create another habit
        self.meditation_habit = Habit.objects.create(
            name='Meditation',
            slug='meditation',
        )
        HabitKeyword.objects.create(habit=self.meditation_habit, keyword='medytacja')

    def test_parse_single_habit_tracked(self):
        """Test parsing a single tracked habit (#)."""
        result = habits_line_to_habits_tracked('#food pizza')

        self.assertEqual(len(result), 1)
        occured, habit, note = result[0]
        self.assertTrue(occured)
        self.assertEqual(habit, self.food_habit)
        self.assertEqual(note, '#food pizza')

    def test_parse_single_habit_skipped(self):
        """Test parsing a single skipped habit (!)."""
        result = habits_line_to_habits_tracked('!food nie dzisiaj')

        self.assertEqual(len(result), 1)
        occured, habit, note = result[0]
        self.assertFalse(occured)
        self.assertEqual(habit, self.food_habit)
        self.assertEqual(note, '!food nie dzisiaj')

    def test_parse_multiple_habits_in_many_lines(self):
        """Test parsing multiple habits in a single line."""
        result = habits_line_to_habits_tracked('#food kebab\n#workout trening')

        self.assertEqual(len(result), 2)

        # First habit
        occured1, habit1, note1 = result[0]
        self.assertTrue(occured1)
        self.assertEqual(habit1, self.food_habit)
        self.assertEqual(note1, '#food kebab')

        # Second habit
        occured2, habit2, note2 = result[1]
        self.assertTrue(occured2)
        self.assertEqual(habit2, self.workout_habit)
        self.assertEqual(note2, '#workout trening')

    def test_parse_multiple_habits_in_one_line(self):
        """Test parsing multiple habits in a single line."""
        result = habits_line_to_habits_tracked('#food kebab #workout trening')

        self.assertEqual(len(result), 2)

        # First habit
        occured1, habit1, note1 = result[0]
        self.assertTrue(occured1)
        self.assertEqual(habit1, self.food_habit)
        self.assertEqual(note1, '#food kebab')

        # Second habit
        occured2, habit2, note2 = result[1]
        self.assertTrue(occured2)
        self.assertEqual(habit2, self.workout_habit)
        self.assertEqual(note2, '#workout trening')

    def test_parse_habit_with_multiple_keywords(self):
        """Test parsing a habit using alternative keyword."""
        # Use 'siłka' keyword which maps to workout habit
        result = habits_line_to_habits_tracked('#siłka dzisiaj')

        self.assertEqual(len(result), 1)
        occured, habit, note = result[0]
        self.assertTrue(occured)
        self.assertEqual(habit, self.workout_habit)
        self.assertEqual(note, '#siłka dzisiaj')

    def test_parse_no_matching_keyword(self):
        """Test parsing when no keyword matches."""
        # 'nonexistent' is not a valid keyword
        result = habits_line_to_habits_tracked('#nonexistent test')

        # Should return empty list when no match
        self.assertEqual(len(result), 0)

    def test_parse_empty_line(self):
        """Test parsing an empty line."""
        result = habits_line_to_habits_tracked('')

        self.assertEqual(len(result), 0)

    def test_parse_line_without_habit_markers(self):
        """Test parsing a line without # or ! markers."""
        result = habits_line_to_habits_tracked('just some text')

        self.assertEqual(len(result), 0)

    def test_parse_mixed_tracked_and_skipped(self):
        """Test parsing a line with both tracked and skipped habits."""
        result = habits_line_to_habits_tracked('#food pizza !medytacja niestety')

        self.assertEqual(len(result), 2)

        # First habit - tracked
        occured1, habit1, note1 = result[0]
        self.assertTrue(occured1)
        self.assertEqual(habit1, self.food_habit)

        # Second habit - skipped
        occured2, habit2, note2 = result[1]
        self.assertFalse(occured2)
        self.assertEqual(habit2, self.meditation_habit)

    def test_parse_unicode_keyword(self):
        """Test parsing with unicode characters in keyword."""
        result = habits_line_to_habits_tracked('#medytacja dziś rano')

        self.assertEqual(len(result), 1)
        occured, habit, note = result[0]
        self.assertTrue(occured)
        self.assertEqual(habit, self.meditation_habit)
        self.assertEqual(note, '#medytacja dziś rano')
