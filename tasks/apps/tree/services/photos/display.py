"""Presigned photo URLs for rendering PhotoAdded events in web pages.

Shared by every page that renders journal entries through the
``journal_added.html`` partial: the trip pages, the diary archive and today.
"""

from . import storage as photo_storage


def attach_photo_urls(events):
    """Add presigned ``thumbnail_url``/``original_url`` to PhotoAdded events.

    Mutates each photo event in place so the shared ``journal_added.html``
    partial can render a miniature (thumbnail) linking to the full original.
    Plain JournalAdded events are left untouched. Falls back to the original
    when the WebP thumbnail has not been generated yet.

    Uses the *web* presign so the signed host is reachable from a desktop
    browser (the device-facing public endpoint targets the Android emulator
    in dev).
    """
    for event in events:
        if not getattr(event, "is_photo", False):
            continue
        event.original_url = photo_storage.presign_get_web(event.original_key)
        event.thumbnail_url = (
            photo_storage.presign_get_web(event.thumbnail_key)
            if event.thumbnail_key
            else None
        )
    return events
