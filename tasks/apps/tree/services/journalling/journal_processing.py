"""
Journal entry processing orchestration.

This module coordinates the processing of journal entries after save,
including reflection extraction and habit tracking.
"""

from .habit_extraction import habits_line_to_habits_tracked
from .reflection_extraction import add_reflection_items


def process_journal_entry(journal_added, skip_habits=False):
    """
    Process a journal entry after it has been saved.

    Extracts reflection items and creates habit tracking entries
    based on the journal content.

    Args:
        journal_added: A saved JournalAdded instance.
        skip_habits: If True, skip habit extraction (used for reflection-only entries).
    """
    # Import here to avoid circular imports
    from ...models import HabitTracked, Thread

    add_reflection_items(journal_added)

    if skip_habits:
        return

    triplets = habits_line_to_habits_tracked(journal_added.comment)

    for occured, habit, note in triplets:
        HabitTracked.objects.create(
            occured=occured,
            habit=habit,
            note=note,
            published=journal_added.published,
            thread=Thread.objects.get(name="Daily"),
        )
