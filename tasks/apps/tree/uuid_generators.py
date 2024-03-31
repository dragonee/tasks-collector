from django.utils.text import slugify

import uuid

BOARD_URL = 'https://schemas.polybrain.org/tasks/boards/{}'

def thread_event_stream_id(url, thread):
    return uuid.uuid5(uuid.NAMESPACE_URL, name=url.format(slugify(thread.name)))


def board_event_stream_id(board):
    return thread_event_stream_id(BOARD_URL, board.thread)

def board_event_stream_id_from_thread(thread):
    return thread_event_stream_id(BOARD_URL, thread)

