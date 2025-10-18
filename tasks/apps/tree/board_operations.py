from django.shortcuts import get_object_or_404

from .models import Board, Thread


def add_task_to_board(text, thread_name):
    """Helper function to add a task to a board"""
    thread = get_object_or_404(Thread, name=thread_name)
    board = Board.objects.filter(thread=thread).order_by('-date_started').first()
    if board:
        board.state.append({
            'children': [],
            'data': {
                'state': 'open',
                'text': text,
                'meaningfulMarkers': {
                    "weeksInList": 0,
                    "important": False,
                    "finalizing": False,
                    "canBeDoneOutsideOfWork": False,
                    "canBePostponed": False,
                    "postponedFor": 0,
                    "madeProgress": False,
                }
            },
            'text': text,
        })
        board.save()
        return board
    return None
