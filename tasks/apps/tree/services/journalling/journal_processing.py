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
        user: Optional user. When given, any reflection line whose base matches
            a task on the user's current board crosses that task once its
            progress (derived from the Reflection) reaches the total. Passed
            only by the console/web journal callers.
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
    """Cross board tasks based on the Reflection ``add_reflection_items`` just
    wrote. Runs after it, so counts are current. For each reflection line (any
    of good/better/best), base-match against the board: a counted task is
    crossed once its derived count reaches the total; a marker-less task is
    crossed because the line was recorded. Writes only the board — the
    Reflection is owned by ``add_reflection_items``.

    The ``services.today`` imports are function-local: importing them at module
    scope would run ``today/__init__`` -> ``operations`` -> ``trips`` -> back
    into ``journalling`` (a cycle).
    """
    from ...models import Reflection, Thread
    from ..today import board_tree
    from ..today.operations import (
        NoBoardError,
        _cross_if_complete,
        _current_board,
        _progress_count,
    )
    from ..today.progress import base_of, parse_progress

    try:
        board = _current_board(user)
    except NoBoardError:
        return

    daily = Thread.objects.filter(name="Daily").first()
    reflection = (
        Reflection.objects.filter(pub_date=published.date(), thread=daily).first()
        if daily is not None
        else None
    )

    changed = False
    for _field, line in extract_reflection_lines(comment):
        base = base_of(line)
        hit = board_tree.find_task_by_base(board.state, base)
        if hit is None:
            continue
        _, _, node = hit
        if parse_progress(board_tree._node_text(node)) is None:
            if board_tree.get_state(node) != "done":
                board_tree.set_state(node, "done")
                changed = True
        elif _cross_if_complete(board, base, _progress_count(reflection, base)):
            changed = True
    if changed:
        board.save()
