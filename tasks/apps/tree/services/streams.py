"""Stream membership upkeep and sharing."""

from django.contrib.auth import get_user_model
from django.db import connection, transaction

from ..models import EventStream, EventStreamAccess, Profile, Thread

_MISSING_HOME_ENTRIES_SQL = """
    INSERT INTO tree_eventstreamentry (stream_id, event_id, added)
    SELECT e.event_stream_id, e.id, e.published
    FROM tree_event e
    ON CONFLICT (stream_id, event_id) DO NOTHING
"""

# What can be shared, and the access sharing gives: a whole trip, observation
# or projected outcome to read; a board to read and change (add, tick and
# commit its tasks). Diaries and habits stay private, and so do the built-in
# boards (Daily, Weekly, big-picture) every user has their own of.
SHARE_ROLES = {
    EventStream.Type.TRIP: EventStreamAccess.Role.VIEWER,
    EventStream.Type.OBSERVATION: EventStreamAccess.Role.VIEWER,
    EventStream.Type.PROJECTED_OUTCOME: EventStreamAccess.Role.VIEWER,
    EventStream.Type.BOARD: EventStreamAccess.Role.EDITOR,
}


class SharingError(Exception):
    """A share or revoke that can't be done; the message says why."""


def ensure_home_entries():
    """Make every event a member of its home stream; returns how many were
    missing.

    ``Event.save`` keeps this true. Events written another way (the previous
    release while this one was being deployed, raw SQL, ``loaddata``) can
    miss their entry; this adds them and changes nothing else.
    """
    with connection.cursor() as cursor:
        cursor.execute(_MISSING_HOME_ENTRIES_SQL)
        return cursor.rowcount


def owned_shareable_stream(owner, stream_id):
    """The shareable stream ``owner`` owns with this id, or None."""
    return (
        EventStream.objects.owned_by(owner)
        .filter(pk=stream_id, type__in=SHARE_ROLES)
        .exclude(board_thread__name__in=Thread.BUILTIN_NAMES)
        .first()
    )


def share_role(stream):
    """The role sharing ``stream`` gives: viewer, or editor for a board."""
    return SHARE_ROLES[stream.type]


def shared_with(stream):
    """The users ``stream`` is shared with, by username."""
    return (
        get_user_model()
        .objects.filter(
            stream_access__stream=stream,
            stream_access__role__in=set(SHARE_ROLES.values()),
        )
        .order_by("username")
    )


@transaction.atomic
def share(owner, stream, username):
    """Let the user called ``username`` into the whole of ``stream``.

    A trip, observation or outcome is shared view only: they can read every
    event in it, now and later, and change nothing. A board is shared to
    edit: they can read and change it and commit it. Sharing again changes
    nothing. Returns the user.

    Raises ``SharingError`` for a stream ``owner`` doesn't own or that can't
    be shared, an unknown username, or the owner themselves.
    """
    if stream is None or owned_shareable_stream(owner, stream.pk) is None:
        raise SharingError("Only its owner can share this.")
    user = get_user_model().objects.filter(username=username).first()
    if user is None:
        raise SharingError(f"There is no user called {username!r}.")
    if user == owner:
        raise SharingError("You already own this.")
    EventStreamAccess.objects.get_or_create(
        stream=stream, user=user, defaults={"role": share_role(stream)}
    )
    return user


@transaction.atomic
def revoke(owner, stream, username):
    """Stop sharing ``stream`` with the user called ``username``. Revoking a
    user it isn't shared with changes nothing.

    A board that was their default board stops being it; they fall back to
    their own Daily board.

    Raises ``SharingError`` for a stream ``owner`` doesn't own or that can't
    be shared.
    """
    if stream is None or owned_shareable_stream(owner, stream.pk) is None:
        raise SharingError("Only its owner can stop sharing this.")
    revoked, _ = (
        EventStreamAccess.objects.filter(stream=stream, user__username=username)
        .exclude(role=EventStreamAccess.Role.OWNER)
        .delete()
    )
    if revoked:
        Profile.objects.filter(
            user__username=username, default_board_thread__board_stream=stream
        ).update(default_board_thread=None)
