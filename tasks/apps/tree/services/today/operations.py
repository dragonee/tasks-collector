"""Orchestrated Today-tab task operations.

Each public operation is wrapped in ``transaction.atomic`` so that the
multi-record write (Board JSON + Plan.focus + Reflection.good) either all
commits or none of it does.
"""

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ...board_operations import board_thread_for
from ...models import Board, JournalAdded, Plan, Reflection, Story, StoryEvent, Thread
from ..trips.operations import StoryNotFoundError, StoryStoppedError
from . import board_tree, text_lines
from .progress import (
    base_of,
    marker_value,
    parse_progress,
    remaining_after,
    render_carried,
    render_count,
    render_progress,
)


class NoBoardError(Exception):
    """No board exists for the user's configured thread."""


@dataclass(frozen=True)
class TodayTask:
    text: str
    done: bool
    mark: Optional[str] = None  # "~" (better) / "^" (best) for boolean tasks


@dataclass(frozen=True)
class BoardItem:
    text: str
    moscow: Optional[str]
    depth: int
    done: bool


def _today(today, published=None):
    if today is not None:
        return today
    if published is not None:
        return published.date()
    return date_cls.today()


def _maybe_add_journal(text_for_marker, note, published, daily, story=None):
    """Record a JournalAdded with ``- [x] <text_for_marker>`` followed by
    the user's free-form note, linked to ``story`` when one is given.

    Skipped when ``note`` is falsy (None or empty string) and there is no
    ``story`` — confirming a check without any text counts as "just tick the
    task", not journal-worthy. "Save to trip" with an empty note is an
    explicit choice, so the marker-only entry is kept and linked.

    Only reached for ``done=True`` completions; the caller (``complete_task``)
    owns the done-state guard. Deliberately bypasses
    ``services.journalling.process_journal_entry``: the ``[x]`` prefix would
    otherwise re-trigger reflection extraction and duplicate the line that
    ``set_task_done`` already wrote to ``Reflection.good``.
    """
    if not note and story is None:
        return
    marker = f"- [x] {text_for_marker}"
    comment = f"{marker}\n{note}" if note else marker
    journal = JournalAdded.objects.create(
        thread=daily,
        comment=comment,
        published=published or timezone.now(),
    )
    if story is not None:
        StoryEvent.objects.create(story=story, event=journal)


def _owned_active_story(user, story_id):
    """Resolve the trip a completion note should be linked to.

    Raises the trips-domain errors so the view layer maps them the same
    way as the trip endpoints (404 not-owned / 409 stopped).
    """
    try:
        story = Story.objects.get(pk=story_id, user=user)
    except Story.DoesNotExist as e:
        raise StoryNotFoundError(
            f"Story #{story_id} not found for user {user.pk}"
        ) from e
    if story.stopped is not None:
        raise StoryStoppedError(f"Story #{story_id} is stopped; cannot add notes.")
    return story


def _daily_thread():
    return Thread.objects.get(name="Daily")


def _current_board(user):
    thread = board_thread_for(user)
    board = Board.objects.filter(thread=thread).order_by("-date_started").first()
    if board is None:
        raise NoBoardError(
            f"No board exists for thread {thread.name!r}; "
            "create one in the web app before using the Android Today endpoints."
        )
    return board


def _progress_count(reflection, base):
    """The task's completed-step count ``N`` = the largest marker value among
    Reflection good/better/best lines whose base matches ``base`` (0 if none)."""
    if reflection is None:
        return 0
    values = []
    for field in ("good", "better", "best"):
        for line in text_lines.split_lines(getattr(reflection, field)):
            if base_of(line) == base:
                value = marker_value(line)
                if value is not None:
                    values.append(value)
    return max(values, default=0)


def _boolean_mark(reflection, line):
    """``(done, mark)`` for a marker-less task line: done if it appears in any
    Reflection field; ``mark`` is ``~`` (better) / ``^`` (best), None for good."""
    if reflection is None:
        return (False, None)
    if text_lines.has_line(reflection.good, line):
        return (True, None)
    if text_lines.has_line(reflection.better, line):
        return (True, "~")
    if text_lines.has_line(reflection.best, line):
        return (True, "^")
    return (False, None)


def plan_tasks(pub_date, thread_name):
    """Return the day's Plan.focus lines as display tasks, deriving state from
    the Reflection (Plan/Board text is never rewritten by progress).

    - Marker-less line: done if it appears in any Reflection field
      (good/better/best), with a ``~``/`^`` mark for better/best.
    - Counted line ``Base (M)``: ``N`` = the largest count logged for ``Base``
      across the fields; display ``(min(N+1, M)/M)``; done when ``N >= M``.

    Order follows the Plan; empty lines are dropped. Returns an empty list when
    the thread doesn't exist or there's no plan for the date.
    """
    thread = Thread.objects.filter(name=thread_name).first()
    if thread is None:
        return []

    plan = Plan.objects.filter(pub_date=pub_date, thread=thread).first()
    reflection = Reflection.objects.filter(pub_date=pub_date, thread=thread).first()

    plan_lines = [l for l in text_lines.split_lines(plan.focus if plan else None) if l]

    tasks = []
    for line in plan_lines:
        progress = parse_progress(line)
        if progress is None:
            done, mark = _boolean_mark(reflection, line)
            tasks.append(TodayTask(text=line, done=done, mark=mark))
        else:
            n = _progress_count(reflection, base_of(line))
            step = min(n + 1, progress.total)
            tasks.append(
                TodayTask(
                    text=render_progress(line, progress, step),
                    done=n >= progress.total,
                )
            )
    return tasks


@transaction.atomic
def list_today_tasks(user, today=None):
    """Return today's Daily Plan lines, each flagged done if it also appears
    in Reflection.good. Unchecked first, original Plan order preserved within
    each group.
    """
    items = plan_tasks(_today(today), "Daily")
    items.sort(key=lambda it: it.done)  # False (not done) sorts before True
    return items


def _flatten_board(nodes, depth, out):
    """Pre-order DFS over the Board.state tree, appending one BoardItem per
    node so parents precede their children and ``depth`` reflects nesting.
    """
    for node in nodes or []:
        markers = (node.get("data") or {}).get("meaningfulMarkers") or {}
        out.append(
            BoardItem(
                text=board_tree._node_text(node),
                moscow=markers.get("moscow"),
                depth=depth,
                done=board_tree.get_state(node) == "done",
            )
        )
        _flatten_board(node.get("children") or [], depth + 1, out)
    return out


def list_board_items(user):
    """Flatten the user's current board into depth-annotated rows for the
    Android 'add from board' picker. Read-only — no transaction needed.
    """
    board = _current_board(user)
    return _flatten_board(board.state, 0, [])


@transaction.atomic
def add_task(user, text, today=None):
    """Ensure the task exists on the board (root-level append if missing)
    and that today's Plan.focus contains the line.

    An in-progress display marker ``(N/K)`` — the form the Android list shows
    for a partly-counted task, carried in verbatim by "Copy to today" / "Move
    to tomorrow" — is canonically rewritten to the count of the work that still
    *remains* (``New task (2/3)`` → ``New task (2)``); see
    ``_add_carried_progress_task``. Plain and already-canonical ``(K)`` tasks
    take the straight path below.
    """
    pub_date = _today(today)

    remaining = remaining_after(text)
    if remaining is not None:
        _add_carried_progress_task(user, text, remaining, pub_date)
        return

    board = _current_board(user)

    if board_tree.find_task_by_text(board.state, text) is None:
        board_tree.append_task_at_root(board.state, text)
        board.save()

    daily = _daily_thread()
    plan, _created = Plan.objects.get_or_create(pub_date=pub_date, thread=daily)
    new_focus = text_lines.add_unique_line(plan.focus, text)
    if new_focus != (plan.focus or ""):
        plan.focus = new_focus
        plan.save()


def _add_carried_progress_task(user, text, remaining, pub_date):
    """Carry an in-progress ``(N/K)`` task forward as a fresh ``(remaining)``
    counter: rename the matching board node's marker to ``(remaining)`` and put
    the canonical single-number line on the day's Plan.focus.

    When only one step remains (``remaining == 1`` — the last item, or a
    finished task whose display capped at ``(K/K)``) the marker is dropped
    altogether and the task carries forward as a plain, counter-less one.

    The board node is matched by base (marker-insensitive) so ``New task (K)`` is
    found regardless of the display marker; its own text layout is preserved and
    only the marker value is rewritten. When the task isn't on the board yet, the
    canonical line is appended at the root.
    """
    board = _current_board(user)
    canonical = render_carried(text, remaining)
    base = base_of(text)

    hit = board_tree.find_task_by_base(board.state, base)
    if hit is None:
        board_tree.append_task_at_root(board.state, canonical)
        board.save()
    else:
        _, _, node = hit
        node_text = board_tree._node_text(node)
        new_node_text = (
            render_carried(node_text, remaining)
            if parse_progress(node_text) is not None
            else canonical
        )
        if node_text != new_node_text:
            board_tree.rename(node, new_node_text)
            board.save()

    daily = _daily_thread()
    plan, _created = Plan.objects.get_or_create(pub_date=pub_date, thread=daily)
    new_focus = text_lines.add_unique_line(plan.focus, canonical)
    if new_focus != (plan.focus or ""):
        plan.focus = new_focus
        plan.save()


@transaction.atomic
def set_task_done(user, text, done, today=None, published=None):
    """Mark the task as done / not-done and sync ``Reflection.good``.

    For plain tasks this flips the board node's ``data.state`` and adds /
    removes the line in ``Reflection.good``. For tasks whose text contains
    a progress marker (e.g. ``Do tasks (3)``, ``(2/4) Walk 1km``), this
    advances or rewinds the marker — see ``_set_task_done_progress``.

    Returns the marker text a journal entry should use — the input ``text``
    for plain tasks, or the rendered progress text (e.g. ``Do tasks (3/3)``)
    for progress tasks — or ``None`` when the request is a no-op (unticking a
    partially-progressed task). Journal creation itself lives in
    ``complete_task``; ``process_journal_entry`` calls this directly and
    ignores the return.
    """
    progress = parse_progress(text)
    if progress is None:
        return _set_task_done_boolean(user, text, done, today, published)
    return _set_task_done_progress(user, text, done, progress, today, published)


@transaction.atomic
def complete_task(
    user, text, done, today=None, note=None, published=None, story_id=None
):
    """Android-edge orchestration: mark the task done / not-done and, for a
    ``done=True`` completion carrying a ``note`` (or a "Save to trip"
    ``story_id``), record a ``JournalAdded`` linked to the optional trip.

    ``story_id`` links that journal entry to an active trip; raises
    ``StoryNotFoundError`` / ``StoryStoppedError`` like the trip endpoints.
    The whole operation is atomic, so a story error rolls back the board and
    reflection writes too.
    """
    marker_text = set_task_done(user, text, done, today=today, published=published)
    if done and marker_text is not None:
        story = _owned_active_story(user, story_id) if story_id is not None else None
        _maybe_add_journal(marker_text, note, published, _daily_thread(), story)


def _set_task_done_boolean(user, text, done, today, published):
    pub_date = _today(today, published)
    board = _current_board(user)

    new_node_state = "done" if done else "open"
    hit = board_tree.find_task_by_text(board.state, text)
    if hit is None:
        node = board_tree.append_task_at_root(board.state, text)
        board_tree.set_state(node, new_node_state)
        board.save()
    else:
        _, _, node = hit
        if board_tree.get_state(node) != new_node_state:
            board_tree.set_state(node, new_node_state)
            board.save()

    daily = _daily_thread()
    reflection, _created = Reflection.objects.get_or_create(
        pub_date=pub_date, thread=daily
    )
    if done:
        new_good = text_lines.add_unique_line(reflection.good, text)
    else:
        new_good = text_lines.remove_line(reflection.good, text)
    if new_good != (reflection.good or ""):
        reflection.good = new_good
        reflection.save()

    return text


def _cross_if_complete(board, base, n):
    """Cross / un-cross the board node matching ``base`` based on whether its
    completed count ``n`` reached the node's own total. No text edits. Returns
    True if the node state changed (caller saves the board)."""
    hit = board_tree.find_task_by_base(board.state, base)
    if hit is None:
        return False
    _, _, node = hit
    node_progress = parse_progress(board_tree._node_text(node))
    total = node_progress.total if node_progress else 1
    new_state = "done" if n >= total else "open"
    if board_tree.get_state(node) != new_state:
        board_tree.set_state(node, new_state)
        return True
    return False


def _set_task_done_progress(user, text, done, progress, today, published):
    """Android-tick progression under the reflection-count model: read the
    task's current count ``N`` from the Reflection, log the next count line
    ``Base (N±1)`` (increment on tick, decrement on untick), and cross the
    matching board node when the count reaches its total. Plan/Board text is
    never rewritten.

    Returns the display marker text for an optional journal entry, or None on a
    no-op (untick at zero).
    """
    pub_date = _today(today, published)
    base = base_of(text)
    daily = _daily_thread()
    reflection, _created = Reflection.objects.get_or_create(
        pub_date=pub_date, thread=daily
    )
    n = _progress_count(reflection, base)

    if done:
        new_n = n + 1
        new_good = text_lines.add_unique_line(
            reflection.good, render_count(text, progress, new_n)
        )
    else:
        if n <= 0:
            return None
        new_n = n - 1
        new_good = text_lines.remove_line(
            reflection.good, render_count(text, progress, n)
        )
    if new_good != (reflection.good or ""):
        reflection.good = new_good
        reflection.save()

    board = _current_board(user)
    if _cross_if_complete(board, base, new_n):
        board.save()

    return render_progress(text, progress, min(new_n + 1, progress.total))


@transaction.atomic
def delete_task(user, text, today=None):
    """Remove the task from the board (only if leaf) and from today's
    Plan.focus. Reflection.good is intentionally left untouched.

    Board removal matches the exact text, so a carried progress task whose node
    was already renamed to its remaining count survives (that node is the work
    moved forward, not deleted). The Plan.focus line is matched by base for
    progress tasks, because the plan stores the canonical ``(K)`` form while the
    caller passes the display ``(N/K)`` form — matching by base finds it either
    way. This is what lets "Move to tomorrow" drop the task off today's plan.
    """
    pub_date = _today(today)
    board = _current_board(user)

    hit = board_tree.find_task_by_text(board.state, text)
    if hit is not None:
        parent_list, idx, node = hit
        if not board_tree.has_children(node):
            parent_list.pop(idx)
            board.save()

    daily = _daily_thread()
    plan = Plan.objects.filter(pub_date=pub_date, thread=daily).first()
    if plan and plan.focus:
        new_focus = _remove_plan_line(plan.focus, text)
        if new_focus != plan.focus:
            plan.focus = new_focus
            plan.save()


def _remove_plan_line(focus, text):
    """Drop ``text`` from a Plan.focus. Plain lines are removed by exact match;
    a progress-marked ``text`` removes the counted line whose base matches
    (marker-insensitive), so the stored ``(K)`` form is found when the caller
    passes the display ``(N/K)`` form."""
    if parse_progress(text) is None:
        return text_lines.remove_line(focus, text)
    base = base_of(text)
    kept = [
        line
        for line in text_lines.split_lines(focus)
        if not (parse_progress(line) is not None and base_of(line) == base)
    ]
    return "\n".join(kept)
