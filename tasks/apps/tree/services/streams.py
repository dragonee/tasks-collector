"""Stream membership upkeep."""

from django.db import connection

_MISSING_HOME_ENTRIES_SQL = """
    INSERT INTO tree_eventstreamentry (stream_id, event_id, added)
    SELECT e.event_stream_id, e.id, e.published
    FROM tree_event e
    ON CONFLICT (stream_id, event_id) DO NOTHING
"""


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
