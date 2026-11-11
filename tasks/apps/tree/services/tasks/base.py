"""Making tasks and letting go of them."""

from ...board_operations import board_thread_for
from ...models import Task, Thread


def create_task(user, text, board=None, board_item_id=None):
    """A new task of ``user``.

    It lives in the stream of ``board`` when it was planned from an item of
    that board, otherwise in the stream of the user's default board: whoever
    can change that board can see and complete the task.
    """
    if board is not None:
        stream_id = board.thread.board_stream_id
    else:
        stream_id = board_thread_for(user).board_stream_id

    return Task.objects.create(
        user=user,
        text=text,
        event_stream_id=stream_id,
        board=board,
        board_item_id=board_item_id,
    )


def board_thread_of(task):
    """The thread of the board whose stream the task lives in."""
    return Thread.objects.get(board_stream_id=task.event_stream_id)


def collect_garbage(tasks):
    """Delete those of ``tasks`` that nothing remembers: never done, on no
    plan, not linked to a board item. A task that was done stays, whatever
    else happens to it."""
    for task in tasks:
        if task.done_count or task.board_id is not None:
            continue
        if task.plan_lines.exists() or task.completions.exists():
            continue
        task.delete()
