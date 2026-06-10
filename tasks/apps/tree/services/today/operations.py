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

from ...models import (
    Board,
    JournalAdded,
    Plan,
    Profile,
    Reflection,
    Story,
    StoryEvent,
    Thread,
)
from ..trips.operations import StoryNotFoundError, StoryStoppedError
from . import board_tree, text_lines
from .progress import parse_progress, render_progress


class NoBoardError(Exception):
    """No board exists for the user's configured thread."""


@dataclass(frozen=True)
class TodayTask:
    text: str
    done: bool


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


def _maybe_add_journal(text_for_marker, note, published, daily, done, story=None):
    """Record a JournalAdded with ``- [x] <text_for_marker>`` followed by
    the user's free-form note, linked to ``story`` when one is given.

    Skipped when:
    - ``done`` is False (the [x] semantics don't fit reversal); or
    - ``note`` is falsy (None or empty string) and there is no ``story`` —
      confirming a check without any text counts as "just tick the task",
      not journal-worthy. "Save to trip" with an empty note is an explicit
      choice, so the marker-only entry is kept and linked.

    Deliberately bypasses ``services.journalling.process_journal_entry``:
    the ``[x]`` prefix would otherwise re-trigger reflection extraction
    and duplicate the line that ``_set_task_done_*`` already wrote to
    ``Reflection.good``.
    """
    if not done or (not note and story is None):
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
def set_task_done(
    user, text, done, today=None, note=None, published=None, story_id=None
):
    """Mark the task as done / not-done.

    For plain tasks this flips the board node's ``data.state`` and adds /
    removes the line in ``Reflection.good``. For tasks whose text contains
    a progress marker (e.g. ``Do tasks (3)``, ``(2/4) Walk 1km``), this
    advances or rewinds the marker — see ``_set_task_done_progress``.

    When ``note is not None`` and ``done is True`` (and the operation
    isn't a no-op), a ``JournalAdded`` is recorded too — see
    ``_maybe_add_journal``. ``story_id`` links that journal entry to an
    active trip ("Save to trip"); raises ``StoryNotFoundError`` /
    ``StoryStoppedError`` like the trip endpoints.
    """
    story = _owned_active_story(user, story_id) if story_id is not None else None
    progress = parse_progress(text)
    if progress is None:
        _set_task_done_boolean(user, text, done, today, note, published, story)
    else:
        _set_task_done_progress(
            user, text, done, progress, today, note, published, story
        )


def _set_task_done_boolean(user, text, done, today, note, published, story=None):
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

    _maybe_add_journal(text, note, published, daily, done, story)


def _next_progress_step(progress, done):
    """Compute the next ``current`` value, or None if the request is a no-op.

    Per the agreed semantics:
    - ``done=True`` always advances by 1 — including past full completion
      (e.g. ``(3/3) → (4/3)`` via the "Add another" action on the
      completed-task dialog).
    - ``done=False`` resets to pristine ``(N)`` if the task was at or
      past full completion, otherwise it's a no-op (unticking a
      partially-progressed task is not meaningful).
    """
    if done:
        return progress.current + 1
    if progress.current < progress.total:
        return None
    return 0


def _set_task_done_progress(
    user, text, done, progress, today, note, published, story=None
):
    next_current = _next_progress_step(progress, done)
    if next_current is None:
        return

    pub_date = _today(today, published)
    new_text = render_progress(text, progress, next_current)
    # A task is "done" whenever its current step is at or past its total —
    # this includes over-quota states like (4/3) reached via "Add another".
    done_before = progress.current >= progress.total
    done_after = next_current >= progress.total

    board = _current_board(user)
    hit = board_tree.find_task_by_text(board.state, text)
    if hit is None:
        node = board_tree.append_task_at_root(board.state, new_text)
    else:
        _, _, node = hit
        board_tree.rename(node, new_text)
    board_tree.set_state(node, "done" if done_after else "open")
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
    if not done_before and done_after:
        # Transition into completion: drop any stale marker (defensive)
        # and add the new fully-complete text.
        cleaned = text_lines.remove_line(reflection.good, text)
        new_good = text_lines.add_unique_line(cleaned, new_text)
    elif done_before and not done_after:
        # Transition out of completion (Reset): remove the old line.
        new_good = text_lines.remove_line(reflection.good, text)
    elif done_before and done_after:
        # Rename in place — (3/3) → (4/3) via "Add another", or any
        # other over-quota advance.
        new_good = text_lines.replace_line(reflection.good, text, new_text)
    else:
        new_good = reflection.good or ""
    if new_good != (reflection.good or ""):
        reflection.good = new_good
        reflection.save()

    _maybe_add_journal(new_text, note, published, daily, done, story)


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
