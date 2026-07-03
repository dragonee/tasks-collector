import uuid

from django.shortcuts import get_object_or_404

from .models import Board, Profile, Thread


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


def add_task_to_board(text, thread_name):
    """Helper function to add a task to a board"""
    thread = get_object_or_404(Thread, name=thread_name)
    board = Board.objects.filter(thread=thread).order_by("-date_started").first()
    if board:
        board.state.append(create_task_item(text))
        board.save()
        return board
    return None


def board_thread_for(user):
    """The thread whose latest board acts as the user's 'current board':
    ``Profile.default_board_thread`` when set, otherwise the Daily thread as a
    fallback so callers never silently no-op on users without a configured
    default.
    """
    profile = (
        Profile.objects.select_related("default_board_thread").filter(user=user).first()
    )
    if profile and profile.default_board_thread is not None:
        return profile.default_board_thread
    return Thread.objects.get(name="Daily")


def current_board_thread_name(user):
    """Name of the user's current board thread (see :func:`board_thread_for`).
    Lets callers name that board when appending a task to it via
    ``boards/append/``, which is keyed by thread name.
    """
    return board_thread_for(user).name
