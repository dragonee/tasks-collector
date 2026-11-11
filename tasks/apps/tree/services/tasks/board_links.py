"""A task and the board item it was planned from.

The item names its task in ``data.taskId``; the task names its item in
``board`` and ``board_item_id``. The task's side is the one the server
trusts when a board tree comes from outside (the web board saves the whole
tree, and may hold one that predates the link).
"""

import uuid

from ...models import Board, Task
from ..boards import items


def _task_ids(values):
    """Those of ``values`` that can be the id of a task. A board tree is
    JSON anyone with the board can write."""
    ids = []
    for value in values:
        try:
            ids.append(uuid.UUID(str(value)))
        except ValueError:
            continue
    return ids


def item_of(task, board):
    """The item of ``board`` that ``task`` was planned from, or None."""
    for item in items.walk(board.state):
        if item.get("id") == task.board_item_id:
            return item
    return None


def link(task, board, item):
    """Record that ``task`` is the task of ``item``. The caller saves the
    board; the task is saved here."""
    item.setdefault("data", {})["taskId"] = str(task.pk)
    task.board = board
    task.board_item_id = item["id"]
    task.event_stream_id = board.thread.board_stream_id
    task.save(update_fields=["board", "board_item_id", "event_stream"])


def _unlink(task):
    task.board = None
    task.board_item_id = None
    task.save(update_fields=["board", "board_item_id"])


def locked_board_of(task):
    """The board ``task`` is linked to, row-locked, or None. Lock it before
    the task: board first is the order every writer takes them in."""
    if task.board_id is None:
        return None
    return Board.objects.select_for_update().filter(pk=task.board_id).first()


def set_ticked(board, task, ticked):
    """Tick or untick the item of ``task`` on ``board`` and save the board,
    if there is anything to change."""
    item = item_of(task, board)
    if item is None or items.is_checked(item) == ticked:
        return
    items.set_checked(item, ticked)
    board.save()


def set_text(board, task):
    """Give the item of ``task`` on ``board`` the task's text and save the
    board, if there is anything to change."""
    item = item_of(task, board)
    if item is None or items.text_of(item) == task.text:
        return
    items.set_text(item, task.text)
    board.save()


def reapply(board):
    """Put the links the tasks know of back onto a tree that came from
    outside, in place. An item names a task only when that task names the
    item; a task whose item is gone is no longer linked.

    Returns whether the tree changed (the caller saves the board).
    """
    by_item = {}
    for task in Task.objects.filter(board=board):
        by_item[task.board_item_id] = task

    changed = False
    seen = set()
    for item in items.walk(board.state):
        task = by_item.get(item.get("id"))
        wanted = str(task.pk) if task is not None else None
        data = item.setdefault("data", {})
        if data.get("taskId") != wanted:
            data["taskId"] = wanted
            changed = True
        if task is not None:
            seen.add(task.pk)

    for task in by_item.values():
        if task.pk not in seen:
            _unlink(task)

    return changed


def follow(boards):
    """After a commit moved items between ``boards``: the tasks follow their
    items. A task whose item left the boards is no longer linked, and neither
    is a task that is done whose item stays (a repeating item is planned anew
    next time).

    Returns the boards whose tree changed (the caller saves them).
    """
    changed = []
    found = {}
    for board in boards:
        for item in items.walk(board.state):
            task_id = (item.get("data") or {}).get("taskId")
            if not task_id:
                continue
            if task_id in found:
                # One item copied onto two boards: the first keeps the task.
                item["data"]["taskId"] = None
                if board not in changed:
                    changed.append(board)
                continue
            found[task_id] = (board, item)

    linked = Task.objects.filter(board__in=[board for board in boards if board.pk])
    tasks = {str(task.pk): task for task in linked}
    elsewhere = _task_ids(pk for pk in found if pk not in tasks)
    for task in Task.objects.filter(pk__in=elsewhere):
        tasks[str(task.pk)] = task

    for task_id, task in tasks.items():
        place = found.pop(task_id, None)
        if place is None:
            _unlink(task)
            continue
        board, item = place
        if task.done:
            item["data"]["taskId"] = None
            if board not in changed:
                changed.append(board)
            _unlink(task)
        elif task.board_id != board.pk or task.board_item_id != item["id"]:
            link(task, board, item)

    # Items naming a task that doesn't exist.
    for board, item in found.values():
        item["data"]["taskId"] = None
        if board not in changed:
            changed.append(board)

    return changed
