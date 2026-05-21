"""Orchestrated Today-tab task operations.

Each public operation is wrapped in ``transaction.atomic`` so that the
multi-record write (Board JSON + Plan.focus + Reflection.good) either all
commits or none of it does.
"""

from dataclasses import dataclass
from datetime import date as date_cls

from django.db import transaction
from django.utils import timezone

from ...models import Board, JournalAdded, Plan, Profile, Reflection, Thread
from . import board_tree, text_lines
from .progress import parse_progress, render_progress


class NoBoardError(Exception):
    """No board exists for the user's configured thread."""


@dataclass(frozen=True)
class TodayTask:
    text: str
    done: bool


def _today(today, published=None):
    if today is not None:
        return today
    if published is not None:
        return published.date()
    return date_cls.today()


def _maybe_add_journal(text_for_marker, note, published, daily, done):
    """Record a JournalAdded with ``- [x] <text_for_marker>`` followed by
    the user's free-form note.

    Skipped when:
    - ``done`` is False (the [x] semantics don't fit reversal); or
    - ``note`` is falsy (None or empty string) — confirming a check
      without any text counts as "just tick the task", not journal-worthy.

    Deliberately bypasses ``services.journalling.process_journal_entry``:
    the ``[x]`` prefix would otherwise re-trigger reflection extraction
    and duplicate the line that ``_set_task_done_*`` already wrote to
    ``Reflection.good``.
    """
    if not done or not note:
        return
    comment = f"- [x] {text_for_marker}\n{note}"
    JournalAdded.objects.create(
        thread=daily,
        comment=comment,
        published=published or timezone.now(),
    )


def _daily_thread():
    return Thread.objects.get(name="Daily")


def _board_thread_for(user):
    """The thread whose latest board acts as the user's 'current board'.

    Uses Profile.default_board_thread when set; otherwise falls back to the
    Daily thread so the operation never silently no-ops on users without a
    configured default.
    """
    try:
        profile = Profile.objects.select_related("default_board_thread").get(user=user)
    except Profile.DoesNotExist:
        return _daily_thread()
    if profile.default_board_thread is not None:
        return profile.default_board_thread
    return _daily_thread()


def _current_board(user):
    thread = _board_thread_for(user)
    board = Board.objects.filter(thread=thread).order_by("-date_started").first()
    if board is None:
        raise NoBoardError(
            f"No board exists for thread {thread.name!r}; "
            "create one in the web app before using the Android Today endpoints."
        )
    return board


@transaction.atomic
def list_today_tasks(user, today=None):
    """Return today's Plan lines, each flagged done if it also appears in
    Reflection.good. Unchecked first, original Plan order preserved within
    each group.
    """
    pub_date = _today(today)
    daily = _daily_thread()

    plan = Plan.objects.filter(pub_date=pub_date, thread=daily).first()
    reflection = Reflection.objects.filter(pub_date=pub_date, thread=daily).first()

    plan_lines = [l for l in text_lines.split_lines(plan.focus if plan else None) if l]
    good = set(text_lines.split_lines(reflection.good if reflection else None))

    items = [TodayTask(text=line, done=line in good) for line in plan_lines]
    items.sort(key=lambda it: it.done)  # False (not done) sorts before True
    return items


@transaction.atomic
def add_task(user, text, today=None):
    """Ensure the task exists on the board (root-level append if missing)
    and that today's Plan.focus contains the line.
    """
    pub_date = _today(today)
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


@transaction.atomic
def set_task_done(user, text, done, today=None, note=None, published=None):
    """Mark the task as done / not-done.

    For plain tasks this flips the board node's ``data.state`` and adds /
    removes the line in ``Reflection.good``. For tasks whose text contains
    a progress marker (e.g. ``Do tasks (3)``, ``(2/4) Walk 1km``), this
    advances or rewinds the marker — see ``_set_task_done_progress``.

    When ``note is not None`` and ``done is True`` (and the operation
    isn't a no-op), a ``JournalAdded`` is recorded too — see
    ``_maybe_add_journal``.
    """
    progress = parse_progress(text)
    if progress is None:
        _set_task_done_boolean(user, text, done, today, note, published)
    else:
        _set_task_done_progress(user, text, done, progress, today, note, published)


def _set_task_done_boolean(user, text, done, today, note, published):
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

    _maybe_add_journal(text, note, published, daily, done)


def _next_progress_step(progress, done):
    """Compute the next ``current`` value, or None if the request is a no-op.

    Per the agreed semantics:
    - ``done=True`` on a non-complete task advances by 1.
    - ``done=False`` on a fully-complete task resets to 0 (pristine).
    - Any other combination (uncheck on partial, tick on complete) is a
      no-op so the caller can return early.
    """
    if done:
        if progress.current >= progress.total:
            return None
        return progress.current + 1
    # done=False: only meaningful when fully complete.
    if progress.current < progress.total:
        return None
    return 0


def _set_task_done_progress(user, text, done, progress, today, note, published):
    next_current = _next_progress_step(progress, done)
    if next_current is None:
        return

    pub_date = _today(today, published)
    new_text = render_progress(text, progress, next_current)
    became_complete = (
        progress.current < progress.total and next_current == progress.total
    )
    left_complete = progress.current == progress.total and next_current < progress.total

    board = _current_board(user)
    hit = board_tree.find_task_by_text(board.state, text)
    if hit is None:
        node = board_tree.append_task_at_root(board.state, new_text)
    else:
        _, _, node = hit
        board_tree.rename(node, new_text)
    board_tree.set_state(node, "done" if next_current == progress.total else "open")
    board.save()

    daily = _daily_thread()
    plan, _created = Plan.objects.get_or_create(pub_date=pub_date, thread=daily)
    if text_lines.has_line(plan.focus, text):
        new_focus = text_lines.replace_line(plan.focus, text, new_text)
    elif not text_lines.has_line(plan.focus, new_text):
        new_focus = text_lines.add_unique_line(plan.focus, new_text)
    else:
        new_focus = plan.focus
    if new_focus != (plan.focus or ""):
        plan.focus = new_focus
        plan.save()

    reflection, _created = Reflection.objects.get_or_create(
        pub_date=pub_date, thread=daily
    )
    if became_complete:
        # Drop any stale marker for this task (defensive) and add the new
        # fully-complete text.
        cleaned = text_lines.remove_line(reflection.good, text)
        new_good = text_lines.add_unique_line(cleaned, new_text)
    elif left_complete:
        new_good = text_lines.remove_line(reflection.good, text)
    else:
        new_good = reflection.good or ""
    if new_good != (reflection.good or ""):
        reflection.good = new_good
        reflection.save()

    _maybe_add_journal(new_text, note, published, daily, done)


@transaction.atomic
def delete_task(user, text, today=None):
    """Remove the task from the board (only if leaf) and from today's
    Plan.focus. Reflection.good is intentionally left untouched.
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
        new_focus = text_lines.remove_line(plan.focus, text)
        if new_focus != plan.focus:
            plan.focus = new_focus
            plan.save()
