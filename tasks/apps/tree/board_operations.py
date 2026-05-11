import uuid

from django.shortcuts import get_object_or_404

from .models import Board, Thread


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
