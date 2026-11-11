import uuid

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from .commit import calculate_changes_per_board, merge
from .models import Board, BoardCommitted, Profile, Thread, default_state


def create_task_item(text):
    """Creates the data structure for a new task."""
    return {
        "id": str(uuid.uuid4()),
        "children": [],
        "data": {
            "state": "open",
            "text": text,
            "meaningfulMarkers": {
                "weeksInList": 0,
                "important": False,
                "finalizing": False,
                "eisenhower": None,
                "moscow": None,
                "canBeDoneOutsideOfWork": False,
                "canBePostponed": False,
                "postponedFor": 0,
                "madeProgress": False,
            },
        },
        "text": text,
    }


@transaction.atomic
def add_task_to_board(user, text, thread_name=None):
    """Add a task to the board called ``thread_name`` among the boards ``user``
    may change (see :func:`board_thread_named`), or to their current board
    (see :func:`board_thread_for`) when no name is given. Returns the board,
    or None when the thread has no board yet; raises ``Http404`` for a name
    the user has no board called.

    The board row is locked from read to save, so a concurrent write to it
    (another append, an Android tick, a commit) can't be overwritten.
    """
    if thread_name is None:
        thread = board_thread_for(user)
    else:
        thread = board_thread_named(user, thread_name)
    if thread is None:
        raise Http404(f"No board called {thread_name!r}.")
    board = (
        Board.objects.filter(thread=thread)
        .order_by("-date_started")
        .select_for_update()
        .first()
    )
    if board:
        board.state.append(create_task_item(text))
        board.save()
        return board
    return None


class UnknownThreadError(Exception):
    """A board item is marked to move to a thread that doesn't exist."""


def _latest_board(user, thread_name):
    """The latest board called ``thread_name`` among the boards ``user`` may
    change (see :func:`board_thread_named`), row-locked until the surrounding
    transaction ends, or a new unsaved one when its thread has none."""
    thread = board_thread_named(user, thread_name)
    if thread is None:
        raise UnknownThreadError(f"no thread named {thread_name!r} to move items to")

    try:
        return Board.objects.filter(thread=thread).select_for_update()[0]
    except IndexError:
        return Board(thread=thread)


@transaction.atomic
def close_board(board, created_by=None):
    """Commit ``board``: record a ``BoardCommitted`` event (written by
    ``created_by``, the board's owner when not given), move the items
    marked with a ``transition`` onto the latest board of that name among the
    boards the committing user may change, and restart ``board`` with the
    items that stay.

    All or nothing: raises ``UnknownThreadError`` before writing anything
    when an item is marked for a thread that doesn't exist.

    The board and the target boards are row-locked and re-read, so a task
    appended or ticked since the caller loaded ``board`` is committed with
    the rest instead of being overwritten.

    Returns the restarted board.
    """
    board = Board.objects.select_for_update().get(pk=board.pk)

    changeset = calculate_changes_per_board(board.state)

    if None in changeset:
        new_state = changeset[None]
        del changeset[None]
    else:
        new_state = default_state()

    # Items move to the boards the committing user may change: their own
    # threads first, then the boards shared with them. An editor of a shared
    # board takes items to their boards, never into the owner's other boards.
    mover = created_by if created_by is not None else board.thread.user
    other_boards = [_latest_board(mover, thread_name) for thread_name in changeset]

    now = timezone.now()

    BoardCommitted.objects.create(
        published=now,
        thread=board.thread,
        focus=board.focus or "",
        before=board.state,
        after=new_state,
        transitions=changeset,
        date_started=board.date_started,
        created_by=created_by,
    )

    for other_board in other_boards:
        other_board.state = merge(other_board.state, changeset[other_board.thread.name])
        other_board.save()

    board.state = new_state
    board.date_started = now
    board.save()

    return board


def board_thread_for(user):
    """The thread whose latest board acts as the user's 'current board':
    ``Profile.default_board_thread`` when set and the user may change its
    board (their own, or shared with them), otherwise the Daily thread as a
    fallback so callers never silently no-op on users without a configured
    default.
    """
    default_id = (
        Profile.objects.filter(user=user)
        .values_list("default_board_thread", flat=True)
        .first()
    )
    if default_id is not None:
        thread = Thread.objects.board_editable_by(user).filter(pk=default_id).first()
        if thread is not None:
            return thread
    return Thread.objects.daily(user)


def board_thread_named(user, name):
    """The thread called ``name`` whose board ``user`` may change, or None.
    Their own thread wins over a shared board of the same name."""
    return Thread.objects.board_editable_by(user).filter(name=name).first()


def current_board_thread_name(user):
    """Name of the user's current board thread (see :func:`board_thread_for`).
    Lets callers name that board when appending a task to it via
    ``boards/append/``, which is keyed by thread name.
    """
    return board_thread_for(user).name
