"""Shared test setup for per-user data.

Tests create threads, boards and profiles through these helpers instead of
the model managers, so that the move to per-user threads (provisioned for
every new user) changes only the bodies below, not every test module.
"""

from ..models import (
    Board,
    EventStream,
    EventStreamEntry,
    Habit,
    HabitKeyword,
    Profile,
    Thread,
)


def make_thread(user, name="Daily"):
    """The thread called ``name`` for ``user``; built-in threads already
    exist, provisioned when the user was created."""
    thread, _ = Thread.objects.get_or_create(user=user, name=name)
    return thread


def make_board(thread, state=None, **fields):
    """The board of ``thread`` with ``state`` and ``fields`` set.

    Built-in threads already have a board (provisioned with their user), which
    is reused so tests see one board per thread; other threads get a new one.
    """
    state = [] if state is None else state
    board = Board.objects.filter(thread=thread).first()
    if board is None:
        return Board.objects.create(thread=thread, state=state, **fields)

    board.state = state
    for name, value in fields.items():
        setattr(board, name, value)
    board.save()
    return board


def make_habit(user, name, slug=None, keywords=(), **fields):
    """A new habit of ``user`` with the given hashtag ``keywords``."""
    habit = Habit.objects.create(
        user=user, name=name, slug=slug or name.lower(), **fields
    )
    for keyword in keywords:
        HabitKeyword.objects.create(habit=habit, keyword=keyword)
    return habit


def trip_links(story=None, event=None, story_id=None):
    """Events' memberships in trip streams (what StoryEvent rows used to be),
    narrowed to a story and/or an event."""
    links = EventStreamEntry.objects.filter(stream__type=EventStream.Type.TRIP)
    if story is not None:
        links = links.filter(stream__story=story)
    if story_id is not None:
        links = links.filter(stream__story__id=story_id)
    if event is not None:
        links = links.filter(event=event)
    return links


def link_to_trip(story, event):
    """Make ``event`` part of ``story`` (a trip)."""
    story.add(event)


def make_profile(user, **fields):
    """The profile for ``user`` (provisioned with the user) with ``fields``
    set."""
    profile, _ = Profile.objects.update_or_create(user=user, defaults=fields)
    return profile
