"""Shared test setup for per-user data.

Tests create threads, boards and profiles through these helpers instead of
the model managers, so that the move to per-user threads (provisioned for
every new user) changes only the bodies below, not every test module.
"""

from ..models import Board, Profile, Thread


def make_thread(user, name="Daily"):
    """The thread called ``name`` for ``user``."""
    thread, _ = Thread.objects.get_or_create(name=name)
    return thread


def make_board(thread, state=None, **fields):
    """A new board on ``thread``."""
    return Board.objects.create(
        thread=thread, state=[] if state is None else state, **fields
    )


def make_profile(user, **fields):
    """The profile for ``user`` with ``fields`` set."""
    return Profile.objects.create(user=user, **fields)
