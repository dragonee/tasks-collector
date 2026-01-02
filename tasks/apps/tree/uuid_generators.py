import uuid
from enum import IntEnum

from django.utils.text import slugify

BOARD_URL = "https://schemas.polybrain.org/tasks/boards/{}"

HABIT_URL = "https://schemas.polybrain.org/tasks/habits/{}"

JOURNAL_URL = "https://schemas.polybrain.org/tasks/journals/{}"


def thread_event_stream_id(url, thread):
    return uuid.uuid5(uuid.NAMESPACE_URL, name=url.format(slugify(thread.name)))


def board_event_stream_id(board):
    return thread_event_stream_id(BOARD_URL, board.thread)


def board_event_stream_id_from_thread(thread):
    return thread_event_stream_id(BOARD_URL, thread)


def journal_added_event_stream_id(obj):
    if hasattr(obj, "thread_id"):
        obj = obj.thread

    return thread_event_stream_id(JOURNAL_URL, obj)


def _habit_event_stream_id(obj):
    if hasattr(obj, "habit_id"):
        obj = obj.habit

    return uuid.uuid5(uuid.NAMESPACE_URL, name=HABIT_URL.format(slugify(obj.name)))


def _habit_event_stream_id_v2(obj):
    if hasattr(obj, "habit_id"):
        obj = obj.habit

    return obj.event_stream_id


class HabitEventVersion(IntEnum):
    V1 = 1
    V2 = 2


CURRENT_HABIT_EVENT_VERSION = HabitEventVersion.V2


def habit_event_stream_id(obj, version=CURRENT_HABIT_EVENT_VERSION):
    if version == HabitEventVersion.V1:
        return _habit_event_stream_id(obj)
    elif version == HabitEventVersion.V2:
        return _habit_event_stream_id_v2(obj)

    raise ValueError(f"Unsupported version: {version}")
