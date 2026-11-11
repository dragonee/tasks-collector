"""Planning by what a line says, and the lock every write to a day takes.

A task typed into a client, a board item added to a plan by its text and a
line ticked in a journal name a task by its text. ``plan_text`` and
``planned_task`` find the task that text means and hand over to
``services.tasks``; nothing is matched by text beyond that lookup.

Every write first row-locks the user's Daily thread (``lock_day``), so two
quick taps on the phone run one after the other instead of both reading the
same plan.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.db import transaction

from ...board_operations import board_thread_for
from ...models import Board, PlanLine, Story, Thread
from ..boards import items
from ..progress import base_of, parse_progress, render_count
from ..tasks import agenda, documents
from ..tasks import operations as tasks
from ..tasks.base import create_task
from ..trips.operations import StoryNotFoundError, StoryStoppedError
from . import board_tree

# How far back an open task of the same text is taken to be the one meant:
# "copy to today" from a day of last week is that task, not a new one.
SAME_TASK_WINDOW = timedelta(days=31)


class NoBoardError(Exception):
    """No board exists for the user's configured thread."""


@dataclass(frozen=True)
class BoardItem:
    text: str
    moscow: Optional[str]
    depth: int
    done: bool
    id: str
    board_id: int
    # Whether the item has a task; otherwise it is an unscheduled task.
    planned: bool


def owned_active_story(user, story_id):
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


def lock_day(user):
    """Row-lock ``user``'s Daily thread until the transaction ends, and
    return it: the lock every write to their Today list takes first."""
    return Thread.objects.select_for_update().get(user=user, name=Thread.DAILY)


def _current_board(user, for_update=False):
    """The latest board of the user's board thread. ``for_update`` row-locks
    it until the surrounding transaction ends."""
    thread = board_thread_for(user)
    boards = Board.objects.filter(thread=thread).order_by("-date_started")
    if for_update:
        boards = boards.select_for_update()
    board = boards.first()
    if board is None:
        raise NoBoardError(
            f"No board exists for thread {thread.name!r}; "
            "create one in the web app before using the Android board picker."
        )
    return board


def _flatten_board(board, nodes, depth, out):
    """Pre-order DFS over the Board.state tree, appending one BoardItem per
    node so parents precede their children and ``depth`` reflects nesting.
    """
    for node in nodes or []:
        data = node.get("data") or {}
        markers = data.get("meaningfulMarkers") or {}
        out.append(
            BoardItem(
                text=items.text_of(node),
                moscow=markers.get("moscow"),
                depth=depth,
                done=items.is_checked(node),
                id=node.get("id"),
                board_id=board.pk,
                planned=bool(data.get("taskId")),
            )
        )
        _flatten_board(board, node.get("children") or [], depth + 1, out)
    return out


def list_board_items(user):
    """Flatten the user's current board into depth-annotated rows for the
    Android 'add from board' picker. Read-only — no transaction needed.
    """
    board = _current_board(user)
    return _flatten_board(board, board.state, 0, [])


def _find_line(plan, text):
    """The line of ``plan`` that ``text`` names, or None."""
    if plan is None:
        return None
    for line in documents.rows(plan):
        if line.content and tasks.same_task_text(line.content, text):
            return line
    return None


def _task_of(user, line):
    """The task of a plan line. A plain line becomes a task now: the task of
    the board item with that text if there is one, and as done as the
    period's reflection says the line was."""
    if line.task_id:
        return line.task

    task = _task_for_board_item(user, line.text) or create_task(user, line.text)
    documents.bind(line, task)
    tasks.adopt(task, documents.reflection_for(line.plan.thread, line.plan.pub_date))
    return task


def _item_named(board, text):
    """The item of ``board`` that ``text`` names: that text exactly, or for
    a counted one with the counter in any form."""
    hit = board_tree.find_unscheduled_task_by_text(board.state, text)
    if hit is None and parse_progress(text) is not None:
        hit = board_tree.find_unscheduled_task_by_base(board.state, base_of(text))
        if hit is not None and parse_progress(items.text_of(hit[2])) is None:
            hit = None
    return hit[2] if hit is not None else None


def _task_for_board_item(user, text, any_board=False):
    """The task of the item called ``text`` on the user's current board, or
    None when the board has no such item (or there is no board). With
    ``any_board`` the other boards the user may change are looked at too."""
    boards = []
    try:
        boards.append(_current_board(user, for_update=True))
    except NoBoardError:
        pass

    if any_board:
        seen = {board.thread_id for board in boards}
        others = (
            Board.objects.editable_by(user)
            .select_for_update()
            .order_by("thread_id", "-date_started")
        )
        for board in others:
            if board.thread_id not in seen:
                seen.add(board.thread_id)
                boards.append(board)

    for board in boards:
        item = _item_named(board, text)
        if item is not None:
            return tasks.task_for_item(user, board, item)
    return None


def planned_task(user, text, day, threads=Thread.BUILTIN_NAMES):
    """The task ``text`` names on the plans ``user`` has for ``day``: the
    day's, the week's, the month's (those of ``threads``). None when no plan
    has such a line. Call it inside a transaction."""
    for thread_name in threads:
        thread = Thread.objects.filter(user=user, name=thread_name).first()
        if thread is None:
            continue
        pub_date = agenda.period_end(thread_name, day)
        line = _find_line(documents.plan_for(thread, pub_date), text)
        if line is not None:
            return _task_of(user, line)
    return None


def _task_planned_elsewhere(user, text, day):
    """The task ``text`` names among what the user has planned around
    ``day``: on the week's or the month's plan, or an open task on another
    recent day."""
    task = planned_task(user, text, day, threads=(Thread.WEEKLY, Thread.BIG_PICTURE))
    if task is not None:
        return task

    recent = (
        PlanLine.objects.filter(
            plan__thread__user=user,
            plan__pub_date__gte=day - SAME_TASK_WINDOW,
            task__isnull=False,
            task__completed_at__isnull=True,
        )
        .select_related("task")
        .order_by("-plan__pub_date")
    )
    for line in recent:
        if tasks.same_task_text(line.task.text, text):
            return line.task
    return None


def _new_task(user, text):
    """A task for ``text`` that names nothing planned. A counter shown as
    "step N of K" starts the new task with the steps before N done."""
    progress = parse_progress(text)
    if progress is None or progress.current == 0:
        return create_task(user, text)

    task = create_task(user, render_count(text, progress, progress.total))
    task.done_count = min(progress.current - 1, progress.total)
    task.save(update_fields=["done_count"])
    return task


def _task_for_text(user, text, day, any_board=False):
    return (
        _task_planned_elsewhere(user, text, day)
        or _task_for_board_item(user, text, any_board=any_board)
        or _new_task(user, text)
    )


@transaction.atomic
def plan_text(user, text, thread_name, pub_date, day, any_board=False):
    """Put the task ``text`` names on ``user``'s plan of the thread called
    ``thread_name`` for ``pub_date``, and return the task.

    That is, in this order: the task of the line the plan has of that text;
    the task of that text already planned for the week or the month of
    ``day``, or for a recent day; the task of the board item of that text (the
    item becomes planned); a new task. A task typed in here is not written
    to the board.

    Raises ``Thread.DoesNotExist`` when the user has no such thread.
    """
    lock_day(user)
    thread = Thread.objects.get(user=user, name=thread_name)
    plan = documents.plan_for(thread, pub_date, create=True)

    line = _find_line(plan, text)
    if line is not None:
        return _task_of(user, line)

    task = _task_for_text(user, text, day, any_board=any_board)
    tasks.plan(task, plan)
    return task


@transaction.atomic
def plan_item(user, board_id, item_id, thread_name, pub_date):
    """Put the task of a board item on ``user``'s plan of the thread called
    ``thread_name`` for ``pub_date``, and return the task. The item becomes
    planned if it was an unscheduled task.

    Raises ``Board.DoesNotExist`` for a board the user may not change,
    ``LookupError`` when it has no such item, and ``Thread.DoesNotExist``.
    """
    lock_day(user)
    board = Board.objects.editable_by(user).select_for_update().get(pk=board_id)
    item = next(
        (item for item in items.walk(board.state) if item.get("id") == item_id),
        None,
    )
    if item is None:
        raise LookupError(f"board {board_id} has no item {item_id!r}")

    thread = Thread.objects.get(user=user, name=thread_name)
    plan = documents.plan_for(thread, pub_date, create=True)
    task = tasks.task_for_item(user, board, item)
    tasks.plan(task, plan)
    return task
