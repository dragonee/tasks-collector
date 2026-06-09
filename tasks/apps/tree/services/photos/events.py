"""Shared helpers for creating photo events from confirmed S3 uploads.

Extracted from ``services.trips.operations`` so the storyless photo path
(``services.photos.standalone``) can reuse the exactly-once lookup, the EXIF
capture-time read, and the Daily-thread resolution without importing the trips
module — which would create a ``trips`` <-> ``photos`` circular import.
"""

from . import storage as photo_storage
from .metadata import read_capture_datetime


class PhotoObjectMissingError(Exception):
    """The presigned upload was never completed (no object in the bucket)."""


def daily_thread():
    """The Daily thread, where diary-style journal/photo events land.

    Deliberately *not* the user's ``Profile.default_board_thread`` (which
    targets boards/tasks and may be the Inbox).
    """
    from ...models import Thread

    return Thread.objects.get(name="Daily")


def existing_event(model, idempotency_key):
    """The event previously created for ``idempotency_key``, or None.

    Used for exactly-once writes: a retried request (whose first response was
    lost) re-uses the existing event instead of creating a duplicate.
    """
    if not idempotency_key:
        return None
    return model.objects.filter(idempotency_key=idempotency_key).first()


def capture_datetime_from_storage(key):
    """Best-effort EXIF capture time of the just-uploaded original.

    Returns None on any failure (download error, non-image, no EXIF date) so a
    missing or unreadable timestamp never blocks the confirm — the caller then
    falls back to the client-supplied ``published``.
    """
    try:
        raw = photo_storage.download_bytes(key)
    except Exception:  # noqa: BLE001 - storage hiccups must not fail confirm
        return None
    return read_capture_datetime(raw)
