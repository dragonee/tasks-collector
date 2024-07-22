from django.utils.text import slugify

import uuid

BOARD_URL = 'https://schemas.polybrain.org/tasks/boards/{}'

HABIT_URL = 'https://schemas.polybrain.org/tasks/habits/{}'

JOURNAL_URL = 'https://schemas.polybrain.org/tasks/journals/{}'

def thread_event_stream_id(url, thread):
    return uuid.uuid5(uuid.NAMESPACE_URL, name=url.format(slugify(thread.name)))


def board_event_stream_id(board):
    return thread_event_stream_id(BOARD_URL, board.thread)

def board_event_stream_id_from_thread(thread):
    return thread_event_stream_id(BOARD_URL, thread)


def journal_added_event_stream_id(obj):
    if hasattr(obj, 'thread_id'):
        obj = obj.thread

    return thread_event_stream_id(JOURNAL_URL, obj)


def habit_event_stream_id(obj):
    if hasattr(obj, 'habit_id'):
        obj = obj.habit

    return uuid.uuid5(uuid.NAMESPACE_URL, name=HABIT_URL.format(slugify(obj.name)))

