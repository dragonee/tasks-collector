"""
Journal entry processing orchestration.

This module coordinates the processing of journal entries after save,
including reflection extraction and habit tracking.
"""

import re

from .habit_extraction import habits_line_to_habits_tracked
from .reflection_extraction import add_reflection_items

QUOTED_LINE_RE = re.compile(r"^[ \t]*>.*(?:\n|$)", re.MULTILINE)


def process_journal_entry(journal_added, skip_habits=False, story=None):
    """
    Process a journal entry after it has been saved.

    Extracts reflection items and creates habit tracking entries
    based on the journal content. Markdown blockquote lines (starting
    with `>`) are stripped before parsing so quoted content is ignored.

    Args:
        journal_added: A saved JournalAdded instance.
        skip_habits: If True, skip habit extraction (used for reflection-only entries).
        story: Optional Story instance. When provided, the JournalAdded itself
            and every HabitTracked extracted from hashtags get linked to the
            story via a StoryEvent row.
    """
    # Import here to avoid circular imports
    from ...models import HabitTracked, StoryEvent, Thread

    comment = QUOTED_LINE_RE.sub("", journal_added.comment)

    add_reflection_items(journal_added, comment=comment)

    if story is not None:
        StoryEvent.objects.create(story=story, event=journal_added)

    if skip_habits:
        return

    triplets = habits_line_to_habits_tracked(comment)

    for occured, habit, note in triplets:
        habit_tracked = HabitTracked.objects.create(
            occured=occured,
            habit=habit,
            note=note,
            published=journal_added.published,
            thread=Thread.objects.get(name="Daily"),
        )
        if story is not None:
            StoryEvent.objects.create(story=story, event=habit_tracked)
