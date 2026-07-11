"""
Journal entry processing orchestration.

This module coordinates the processing of journal entries after save,
including reflection extraction and habit tracking.
"""

import re

from .habit_extraction import habits_line_to_habits_tracked
from .reflection_extraction import add_reflection_items, extract_reflection_lines

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
            and every HabitTracked extracted from hashtags get linked to the
            story via a StoryEvent row.
        user: Optional user. When given, every ``[x]`` (good) line whose text
            matches a task on the user's current board also ticks that task
            via ``set_task_done`` — advancing progress markers just like the
            Android tick. Passed only by the console/web journal callers.
    """
    # Import here to avoid circular imports
    from ...models import HabitTracked, StoryEvent, Thread

    comment = QUOTED_LINE_RE.sub("", journal_added.comment)

    add_reflection_items(journal_added, comment=comment)

    if user is not None:
        _check_matching_board_tasks(user, comment, journal_added.published)

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


def _check_matching_board_tasks(user, comment, published):
    """Tick each board task whose text matches a ``[x]`` (good) reflection line.

    ``set_task_done`` handles progress markers, so ``[x] Do tasks (2/3)``
    advances the matching task the same way the Android tick does. Runs after
    ``add_reflection_items`` so a completing progress transition self-corrects
    the reflection line; matching is exact, so an unmatched line never creates
    a phantom board task.

    The ``services.today`` imports are function-local: importing them at module
    scope would run ``today/__init__`` -> ``operations`` -> ``trips`` -> back
    into ``journalling`` (a cycle).
    """
    from ..today import board_tree
    from ..today.operations import NoBoardError, _current_board, set_task_done

    try:
        board = _current_board(user)
    except NoBoardError:
        return

    for field, line in extract_reflection_lines(comment):
        if field != "good":
            continue
        if board_tree.find_task_by_text(board.state, line) is not None:
            set_task_done(user, line, done=True, published=published)
