"""
Journal entry processing orchestration.

This module coordinates the processing of journal entries after save,
including reflection extraction and habit tracking.
"""

import re

from .habit_extraction import habits_line_to_habits_tracked
from .reflection_extraction import add_reflection_items

QUOTED_LINE_RE = re.compile(r"^[ \t]*>.*(?:\n|$)", re.MULTILINE)


def process_journal_entry(journal_added, skip_habits=False, story=None, user=None):
    """
    Process a journal entry after it has been saved.

    Extracts reflection items and creates habit tracking entries
    based on the journal content. Markdown blockquote lines (starting
    with `>`) are stripped before parsing so quoted content is ignored.

    Args:
        journal_added: A saved JournalAdded instance.
        skip_habits: If True, skip habit extraction (used for reflection-only entries).
        story: Optional Story instance. When provided, the JournalAdded itself
            and every HabitTracked extracted from hashtags are added to the
            trip (members of its stream).
        user: Optional user. When given, a reflection line may also name an
            item of their current board (see ``add_reflection_items``). Passed
            only by the console/web journal callers.
    """
    # Import here to avoid circular imports
    from ...models import HabitTracked, Thread

    comment = QUOTED_LINE_RE.sub("", journal_added.comment)

    add_reflection_items(journal_added, comment=comment, user=user)

    # An anchor says which task a line is about; once that is recorded it is
    # noise in an entry people read (the diary, a trip, a shared page).
    from ..tasks.documents import strip_anchors

    without_anchors = strip_anchors(journal_added.comment)
    if without_anchors != journal_added.comment:
        journal_added.comment = without_anchors
        journal_added.save(update_fields=["comment"])

    if story is not None:
        story.add(journal_added)

    if skip_habits:
        return

    # Hashtags name the habits of whoever wrote the entry, and are tracked on
    # their Daily thread.
    author_id = journal_added.thread.user_id

    triplets = habits_line_to_habits_tracked(comment, author_id)
    if not triplets:
        return

    daily = Thread.objects.daily(author_id)

    for occured, habit, note in triplets:
        habit_tracked = HabitTracked.objects.create(
            occured=occured,
            habit=habit,
            note=note,
            published=journal_added.published,
            thread=daily,
            created_by_id=journal_added.created_by_id,
        )
        if story is not None:
            story.add(habit_tracked)
