"""
Reflection extraction from journal entries.

This module contains logic for parsing journal entries and extracting
reflection items (good/better/best) to add to the appropriate Reflection.
"""

import re
from calendar import monthrange
from datetime import timedelta

from django.db import transaction

REFLECTION_LINE_PREFIXES = (
    ("[x] ", "good"),
    ("[~] ", "better"),
    ("[^] ", "best"),
)

# Optional leading whitespace and an optional markdown list bullet (``-``,
# ``*`` or ``+``) before the marker, so both ``[x] foo`` and the
# markdown-checkbox style ``- [x] foo`` are accepted and strip to ``foo``.
# This mirrors the ``- [x] <text>`` format the Android tick itself records.
_LEADING_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]\s+)?")


def extract_reflection_lines(note):
    """
    Extract reflection lines from a journal note.

    Looks for lines starting with reflection prefixes:
    - [x] for "good" items
    - [~] for "better" items
    - [^] for "best" items

    A leading markdown list bullet (``- ``, ``* `` or ``+ ``) and surrounding
    whitespace are stripped first, so ``- [x] foo`` yields ``foo`` — matching
    the board task's text rather than ``- foo``.

    CRLF / CR line endings are normalized to LF before splitting (the CLI's
    ``sanitize_string`` stores ``\\r\\n``), so a stray ``\\r`` never trails the
    extracted content — otherwise ``foo\\r`` would neither dedupe nor match the
    board task ``foo``.

    A progress marker is coerced to single-number ``(K)`` form (``coerce_to_count``),
    so a client may send either ``New task (1)`` or the displayed ``New task (1/3)``
    and both store/match as ``New task (1)``.

    Args:
        note: The journal note text to parse.

    Returns:
        List of (field_name, line_content) tuples.
    """
    # Lazy: ``today`` at module scope would cycle back through journalling.
    from ..progress import coerce_to_count

    normalized = note.replace("\r\n", "\n").replace("\r", "\n")
    result = []
    for raw_line in normalized.split("\n"):
        line = _LEADING_LIST_MARKER_RE.sub("", raw_line, count=1)
        for prefix, field in REFLECTION_LINE_PREFIXES:
            if line.startswith(prefix):
                result.append((field, coerce_to_count(line[len(prefix) :])))
                break
    return result


def reflection_date(journal_added):
    """The date of the reflection a journal entry's lines go into: the day it
    was written for a daily entry, the end of the week for one on the Weekly
    thread and the end of the month for one on big-picture, so that a whole
    week or month contributes to one reflection."""
    pub_date = journal_added.published.date()

    if journal_added.thread.name == "Weekly":
        pub_date = pub_date + timedelta(days=(6 - pub_date.weekday()))

    if journal_added.thread.name == "big-picture":
        pub_date = pub_date.replace(day=monthrange(pub_date.year, pub_date.month)[1])

    return pub_date


def _add_once(reflection, field, text, task=None):
    """Add the line to the reflection unless that field already says it."""
    from ..tasks import documents

    if any(row.text == text for row in documents.rows(reflection, field)):
        return
    documents.append_reflection_line(reflection, field, text, task=task)


def _record_on_task(task, author, field, text, day, at, reflection, wording=None):
    """A reflection line that names a task: do the steps of the task the line
    says are done. A line about a task already that far along (a week's
    reflection repeating a day's) is added as a line of the task, and nothing
    is done twice. ``wording`` is the line as its author put it, when it
    named the task by its anchor and not by its text."""
    from ..progress import marker_value, parse_progress
    from ..tasks import operations as tasks

    if parse_progress(task.text) is None:
        steps = 0 if task.done else 1
    elif parse_progress(text) is not None:
        steps = marker_value(text) - task.done_count
    else:
        steps = 1

    if steps <= 0:
        _add_once(reflection, field, text, task=task)
        return

    for _ in range(steps):
        tasks.complete(
            task,
            author,
            day=day,
            at=at,
            mark=tasks.MARK_BY_FIELD[field],
            reflection=reflection,
            wording=wording if steps == 1 else None,
        )
        task.refresh_from_db()


def _tick_unscheduled_task(item, text, daily_reflection):
    """A reflection line that names an unscheduled task on the board: tick
    it. One with a step counter is ticked once the day's reflection has
    counted up to its total. Returns whether the item changed."""
    from ..boards import items
    from ..progress import base_of, marker_value, parse_progress
    from ..tasks import documents

    progress = parse_progress(items.text_of(item))
    if progress is None:
        checked = True
    else:
        rows = documents.rows(daily_reflection) if daily_reflection else []
        steps = max(
            (
                marker_value(row.text) or 0
                for row in rows
                if base_of(row.text) == base_of(text)
            ),
            default=0,
        )
        checked = steps >= progress.total

    if items.is_checked(item) == checked:
        return False
    items.set_checked(item, checked)
    return True


@transaction.atomic
def add_reflection_items(journal_added, comment=None, user=None):
    """
    Extract reflection items from a journal entry and record them.

    Each line marked ``[x]`` / ``[~]`` / ``[^]`` goes to the good / better /
    best of the reflection of the journal's thread (see ``reflection_date``).
    What the line's text names decides what else happens:

    - a task, by the anchor the line ends with ("[x] Called them ^t91bd0a44"),
      or by its text when its author has it planned for that day, week or
      month: the task is completed (a counted one by as many steps as the
      line says), and the line is the task's;
    - otherwise, when ``user`` is given, an item of their current board: the
      item's task is completed if it has one, else the unscheduled task is
      ticked;
    - otherwise nothing: it is a line of its own.

    Text is only used here, to find what a typed line means.

    Args:
        journal_added: A JournalAdded instance to extract reflections from.
        comment: Optional pre-processed comment text. Defaults to
            ``journal_added.comment``.
        user: Whose board a line may name. Passed by the console and web
            journal callers.
    """
    # Imports here to avoid circular imports: ``services.today`` and
    # ``services.tasks`` reach ``trips``, which imports ``journalling``.
    from ...models import ReflectionLine, Task, Thread
    from ..progress import base_of
    from ..tasks import documents
    from ..today import board_tree
    from ..today import operations as today

    if comment is None:
        comment = journal_added.comment

    reflection_lines = extract_reflection_lines(comment)

    if not reflection_lines:
        return

    author = journal_added.thread.user
    day = journal_added.published.date()

    today.lock_day(author)
    reflection = documents.reflection_for(
        journal_added.thread, reflection_date(journal_added), create=True
    )

    for field, text in reflection_lines:
        field = ReflectionLine.Field(field)

        text, anchor = documents.split_anchor(text)
        task = wording = None
        if anchor is not None:
            task = Task.objects.editable_by(author).filter(anchor=anchor).first()
            wording = text
        if task is None:
            task = today.planned_task(author, text, day)
            wording = None
        board = item = None
        if task is None and user is not None:
            # Read anew for each line: completing a task saves its board.
            try:
                board = today._current_board(user, for_update=True)
            except today.NoBoardError:
                board = None
        if board is not None:
            hit = board_tree.find_unscheduled_task_by_base(board.state, base_of(text))
            if hit is not None:
                item = hit[2]
                task_id = (item.get("data") or {}).get("taskId")
                task = Task.objects.filter(
                    pk=task_id, completed_at__isnull=True
                ).first()

        if task is not None:
            _record_on_task(
                task,
                author,
                field,
                text,
                day,
                journal_added.published,
                reflection,
                wording=wording,
            )
            continue

        _add_once(reflection, field, text)

        if item is not None:
            daily = Thread.objects.filter(user=user, name=Thread.DAILY).first()
            daily_reflection = (
                documents.reflection_for(daily, day) if daily is not None else None
            )
            if _tick_unscheduled_task(item, text, daily_reflection):
                board.save()
