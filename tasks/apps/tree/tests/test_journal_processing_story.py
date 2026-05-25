from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ..models import HabitTracked, JournalAdded, Story, StoryEvent, Thread
from ..services.journalling import process_journal_entry


class JournalProcessingWithStoryTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily, _ = Thread.objects.get_or_create(name="Daily")

    def _journal(self, comment):
        return JournalAdded.objects.create(
            thread=self.daily, comment=comment, published=timezone.now()
        )

    def test_no_story_kwarg_preserves_existing_behavior(self):
        journal = self._journal("plain entry, no story arg")
        process_journal_entry(journal)
        self.assertFalse(StoryEvent.objects.filter(event=journal).exists())

    def test_story_kwarg_links_journal_only_when_no_hashtags(self):
        story = Story.objects.create(user=self.user, title="t")
        journal = self._journal("just a thought")
        process_journal_entry(journal, story=story)
        self.assertEqual(
            StoryEvent.objects.filter(story=story, event=journal).count(), 1
        )
        self.assertEqual(StoryEvent.objects.filter(story=story).count(), 1)

    def test_story_kwarg_links_journal_and_extracted_habit_tracked(self):
        story = Story.objects.create(user=self.user, title="t")
        journal = self._journal("#poi lat=10 lng=20\nseaside")
        process_journal_entry(journal, story=story)
        # 1 journal + 1 habit-tracked = 2 story_event rows
        self.assertEqual(StoryEvent.objects.filter(story=story).count(), 2)
        habits = HabitTracked.objects.filter(habit__slug="poi")
        self.assertEqual(habits.count(), 1)
        self.assertTrue(
            StoryEvent.objects.filter(story=story, event=habits.first()).exists()
        )

    def test_skip_habits_skips_habit_linking_but_still_links_journal(self):
        story = Story.objects.create(user=self.user, title="t")
        journal = self._journal("#poi lat=1 lng=2\nignore habits")
        process_journal_entry(journal, skip_habits=True, story=story)
        self.assertEqual(StoryEvent.objects.filter(story=story).count(), 1)
        self.assertFalse(HabitTracked.objects.filter(habit__slug="poi").exists())
