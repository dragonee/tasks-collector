"""Standalone (storyless) photo operations.

A standalone photo is the same ``PhotoAdded`` event as a trip photo — it lands
on the Daily thread and runs through the journalling pipeline so a ``#poi`` line
still creates a HabitTracked — except it is **not** linked to any Story (no
``StoryEvent`` row). The only structural difference is the S3 key prefix
(``photos/{user}/`` instead of ``trips/{user}/{story}/``), which doubles as the
ownership signal for the full-original endpoint.

Kept in the ``photos`` package (not ``trips``) so it shares the photo plumbing
without importing the trips module, avoiding a ``trips`` <-> ``photos`` cycle.
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ...models import PhotoAdded
from ..journalling import process_journal_entry
from . import storage as photo_storage
from .events import PhotoObjectMissingError, daily_thread, existing_event
from .keys import photo_key, photo_key_belongs_to


@transaction.atomic
def presign_standalone_photo(user, content_type):
    """Allocate an S3 key and return a presigned PUT URL for a storyless photo.

    Raises ``ValueError`` for an unsupported content type.
    """
    key = photo_key(user.pk, content_type)
    url = photo_storage.presign_put(key, content_type)
    expires_at = timezone.now() + timedelta(seconds=settings.PHOTO_PRESIGN_PUT_TTL)
    return {"key": key, "upload_url": url, "expires_at": expires_at.isoformat()}


@transaction.atomic
def add_standalone_photo(
    user, key, comment, content_type, published=None, idempotency_key=None
):
    """Confirm an uploaded storyless photo: create a ``PhotoAdded`` on the Daily
    thread and run it through the journalling pipeline (so a ``#poi`` line in
    ``comment`` still creates a HabitTracked). Enqueues the thumbnail task on
    commit. Creates no ``StoryEvent`` — the photo belongs to no trip.

    Raises ``PhotoObjectMissingError`` if the object isn't in the bucket (or the
    key doesn't belong to this user's ``photos/{user}/`` prefix).

    Unlike a trip photo, a standalone photo is timestamped with when it was
    *added* (the client-supplied ``published``, i.e. now), **not** the image's
    EXIF/capture time — so its event_stream_id lands on the day it was filed.

    ``idempotency_key`` makes the confirm exactly-once: a retry carrying a key
    that already produced a photo returns that same photo.
    """
    existing = existing_event(PhotoAdded, idempotency_key)
    if existing is not None:
        return existing

    if not photo_key_belongs_to(key, user.pk):
        raise PhotoObjectMissingError(f"key {key!r} not under this user's prefix")
    if not photo_storage.object_exists(key):
        raise PhotoObjectMissingError(f"no uploaded object at {key!r}")

    try:
        # Nested savepoint so a unique-key collision (concurrent retry) rolls
        # back only this insert, leaving the outer transaction usable.
        with transaction.atomic():
            photo = PhotoAdded.objects.create(
                thread=daily_thread(),
                comment=comment,
                original_key=key,
                content_type=content_type,
                published=published or timezone.now(),
                idempotency_key=idempotency_key,
            )
            process_journal_entry(photo, story=None)
    except IntegrityError:
        existing = existing_event(PhotoAdded, idempotency_key)
        if existing is not None:
            return existing
        raise

    # Import here to avoid importing celery tasks at module load.
    from ...tasks import generate_photo_thumbnail

    transaction.on_commit(lambda: generate_photo_thumbnail.delay(photo.pk))
    return photo
