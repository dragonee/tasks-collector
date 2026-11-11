"""Stream membership upkeep and sharing."""

from django.contrib.auth import get_user_model
from django.db import connection, transaction

from ..models import EventStream, EventStreamAccess

_MISSING_HOME_ENTRIES_SQL = """
    INSERT INTO tree_eventstreamentry (stream_id, event_id, added)
    SELECT e.event_stream_id, e.id, e.published
    FROM tree_event e
    ON CONFLICT (stream_id, event_id) DO NOTHING
"""

# What can be shared: a whole trip, observation or projected outcome. Diaries,
# boards and habits stay private.
SHAREABLE_TYPES = (
    EventStream.Type.TRIP,
    EventStream.Type.OBSERVATION,
    EventStream.Type.PROJECTED_OUTCOME,
)


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
        .filter(pk=stream_id, type__in=SHAREABLE_TYPES)
        .first()
    )


def viewers(stream):
    """The users ``stream`` is shared with, by username."""
    return (
        get_user_model()
        .objects.filter(
            stream_access__stream=stream,
            stream_access__role=EventStreamAccess.Role.VIEWER,
        )
        .order_by("username")
    )


@transaction.atomic
def share(owner, stream, username):
    """Let the user called ``username`` see the whole of ``stream``.

    View only: they can read every event in it, now and later, and change
    nothing. Sharing again changes nothing. Returns the viewer.

    Raises ``SharingError`` for a stream ``owner`` doesn't own or that can't
    be shared, an unknown username, or the owner themselves.
    """
    if stream is None or owned_shareable_stream(owner, stream.pk) is None:
        raise SharingError("Only its owner can share this.")
    viewer = get_user_model().objects.filter(username=username).first()
    if viewer is None:
        raise SharingError(f"There is no user called {username!r}.")
    if viewer == owner:
        raise SharingError("You already own this.")
    EventStreamAccess.objects.get_or_create(
        stream=stream,
        user=viewer,
        defaults={"role": EventStreamAccess.Role.VIEWER},
    )
    return viewer


@transaction.atomic
def revoke(owner, stream, username):
    """Stop sharing ``stream`` with the user called ``username``. Revoking a
    user it isn't shared with changes nothing.

    Raises ``SharingError`` for a stream ``owner`` doesn't own or that can't
    be shared.
    """
    if stream is None or owned_shareable_stream(owner, stream.pk) is None:
        raise SharingError("Only its owner can stop sharing this.")
    EventStreamAccess.objects.filter(
        stream=stream,
        user__username=username,
        role=EventStreamAccess.Role.VIEWER,
    ).delete()
