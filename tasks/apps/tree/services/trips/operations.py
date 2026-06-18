"""Orchestrated Trip (Story) operations.

Each public mutator is wrapped in ``transaction.atomic`` so multi-record
writes (Story + JournalAdded + StoryEvent + possibly HabitTracked)
either all commit or none do.
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ...models import JournalAdded, PhotoAdded, SharedStory, Story, StoryEvent
from ..journalling import process_journal_entry
from ..photos import key_belongs_to, original_key, photo_key_belongs_to
from ..photos import storage as photo_storage
from ..photos.events import (
    PhotoObjectMissingError,
    capture_datetime_from_storage,
    daily_thread,
    existing_event,
)
from .titles import default_title

# ``PhotoObjectMissingError`` is imported from ``..photos.events`` and re-exported
# here so ``services.trips`` keeps its existing public surface.


class StoryNotFoundError(Exception):
    """No Story with the given id exists for this user."""


class StoryStoppedError(Exception):
    """The Story is already stopped; no further events can be attached."""


def _journal_thread_for(user):
    """Resolve the Thread used for a trip note's/photo's JournalAdded.

    Trip notes are diary-style entries, so they always go to the Daily thread.
    """
    return daily_thread()


def _get_owned_story(user, story_id):
    try:
        return Story.objects.get(pk=story_id, user=user)
    except Story.DoesNotExist as e:
        raise StoryNotFoundError(
            f"Story #{story_id} not found for user {user.pk}"
        ) from e


@transaction.atomic
def start_trip(user, title=None, type_=Story.Type.TRIP, started=None):
    """Create and persist a new Story for the user.

    If ``title`` is blank or None, auto-generate one from ``started``.
    """
    started = started or timezone.now()
    final_title = title if (title and title.strip()) else default_title(started)
    return Story.objects.create(
        user=user,
        type=type_,
        title=final_title,
        started=started,
    )


@transaction.atomic
def stop_trip(user, story_id):
    """Set Story.stopped to now. Idempotent: re-stopping is a no-op."""
    story = _get_owned_story(user, story_id)
    if story.stopped is None:
        story.stopped = timezone.now()
        story.save(update_fields=["stopped"])
    return story


@transaction.atomic
def update_trip(user, story_id, title=None):
    """Rename a trip. A blank/None title is a no-op."""
    story = _get_owned_story(user, story_id)
    if title is not None and title.strip():
        story.title = title.strip()
        story.save(update_fields=["title"])
    return story


@transaction.atomic
def share_trip(user, story_id):
    """Create-or-get the public share link for a trip.

    Works for stopped trips too — sharing a finished trip is the common case.
    """
    story = _get_owned_story(user, story_id)
    share, _ = SharedStory.objects.get_or_create(story=story)
    return share


@transaction.atomic
def unshare_trip(user, story_id):
    """Delete the share link, killing the public URL permanently.

    Idempotent: unsharing an unshared trip is a no-op. Returns the story.
    """
    story = _get_owned_story(user, story_id)
    SharedStory.objects.filter(story=story).delete()
    return story


def get_shared_story(share_uuid):
    """Public (unauthenticated) lookup: the SharedStory for a share UUID,
    or None. ``select_related`` so callers get the story in the same query.
    """
    return SharedStory.objects.select_related("story").filter(uuid=share_uuid).first()


@transaction.atomic
def add_trip_note(user, story_id, comment, published=None, idempotency_key=None):
    """Create a JournalAdded linked to ``story``, processed through the
    journalling pipeline so embedded hashtags create HabitTracked
    entries that are also linked to the story.

    Raises ``StoryStoppedError`` if the story is already stopped.

    ``idempotency_key`` makes the write exactly-once: a retry carrying a key
    that already produced a note returns that same note. The lookup runs
    *before* the stopped check so re-delivering an already-saved note succeeds
    even if the trip was stopped in the meantime.
    """
    story = _get_owned_story(user, story_id)

    existing = existing_event(JournalAdded, idempotency_key)
    if existing is not None:
        return existing

    if story.stopped is not None:
        raise StoryStoppedError(f"Story #{story_id} is stopped; cannot add new notes.")

    try:
        # Nested savepoint so a unique-key collision (concurrent retry) rolls
        # back only this insert, leaving the outer transaction usable for the
        # re-fetch below.
        with transaction.atomic():
            journal_added = JournalAdded.objects.create(
                thread=_journal_thread_for(user),
                comment=comment,
                published=published or timezone.now(),
                idempotency_key=idempotency_key,
            )
            process_journal_entry(journal_added, story=story)
    except IntegrityError:
        existing = existing_event(JournalAdded, idempotency_key)
        if existing is not None:
            return existing
        raise
    return journal_added


@transaction.atomic
def presign_photo_upload(user, story_id, content_type, web=False):
    """Allocate an S3 key and return a presigned PUT URL for a photo upload.

    ``web=True`` signs the browser-reachable endpoint (the device-facing public
    endpoint targets the Android emulator host in dev, unreachable from a
    desktop browser); the default signs the device-facing endpoint.

    Raises ``StoryNotFoundError`` (not owned), ``StoryStoppedError`` (stopped),
    or ``ValueError`` (unsupported content type).
    """
    story = _get_owned_story(user, story_id)
    if story.stopped is not None:
        raise StoryStoppedError(f"Story #{story_id} is stopped; cannot add photos.")
    key = original_key(user.pk, story_id, content_type)
    presign = photo_storage.presign_put_web if web else photo_storage.presign_put
    url = presign(key, content_type)
    expires_at = timezone.now() + timedelta(seconds=settings.PHOTO_PRESIGN_PUT_TTL)
    return {"key": key, "upload_url": url, "expires_at": expires_at.isoformat()}


@transaction.atomic
def add_trip_photo(
    user, story_id, key, comment, content_type, published=None, idempotency_key=None
):
    """Confirm an uploaded photo: create a PhotoAdded linked to ``story`` and
    run it through the journalling pipeline (so a ``#poi`` line in ``comment``
    still creates a HabitTracked). Enqueues the thumbnail task on commit.

    Raises ``StoryStoppedError`` if stopped, ``PhotoObjectMissingError`` if the
    object isn't in the bucket (or the key doesn't belong to this user/story).

    ``idempotency_key`` makes the confirm exactly-once: a retry carrying a key
    that already produced a photo returns that same photo (checked before the
    stopped/object existence guards, so a re-delivered confirm succeeds even
    after the trip stopped or the S3 object was swept).
    """
    story = _get_owned_story(user, story_id)

    existing = existing_event(PhotoAdded, idempotency_key)
    if existing is not None:
        return existing

    if story.stopped is not None:
        raise StoryStoppedError(f"Story #{story_id} is stopped; cannot add photos.")
    if not key_belongs_to(key, user.pk, story_id):
        raise PhotoObjectMissingError(f"key {key!r} not under this story's prefix")
    if not photo_storage.object_exists(key):
        raise PhotoObjectMissingError(f"no uploaded object at {key!r}")

    # Prefer the time the photo was taken (EXIF) over upload time. Falls back
    # to the client-supplied ``published`` (the gallery's DATE_TAKEN) and then
    # to now. Done here so the pre_save signal computes event_stream_id from
    # the correct date.
    captured = capture_datetime_from_storage(key)

    try:
        # Nested savepoint so a unique-key collision (concurrent retry) rolls
        # back only this insert, leaving the outer transaction usable.
        with transaction.atomic():
            photo = PhotoAdded.objects.create(
                thread=_journal_thread_for(user),
                comment=comment,
                original_key=key,
                content_type=content_type,
                published=captured or published or timezone.now(),
                idempotency_key=idempotency_key,
            )
            process_journal_entry(photo, story=story)
    except IntegrityError:
        existing = existing_event(PhotoAdded, idempotency_key)
        if existing is not None:
            return existing
        raise

    # Import here to avoid importing celery tasks at module load.
    from ...tasks import generate_photo_thumbnail

    transaction.on_commit(lambda: generate_photo_thumbnail.delay(photo.pk))
    return photo


def presign_photo_original(user, event_id):
    """Fresh presigned GET URL for the full-resolution original of a photo the
    user owns.

    Ownership is resolved two ways so this serves both trip photos and
    standalone ones: a trip photo is owned if a ``StoryEvent`` links it to one
    of the user's Stories; a standalone photo (no ``StoryEvent``) is owned if
    its ``original_key`` lives under the user's ``photos/{user}/`` prefix (the
    Daily thread is global, so the key prefix is the only owner signal).

    Raises ``StoryNotFoundError`` if no such owned photo exists (404-safe).
    """
    photo = PhotoAdded.objects.filter(pk=event_id).first()
    if photo is None:
        raise StoryNotFoundError(f"Photo #{event_id} not found")
    entry = StoryEvent.objects.select_related("story").filter(event_id=event_id).first()
    if entry is not None:
        owned = entry.story.user_id == user.id
    else:
        owned = photo_key_belongs_to(photo.original_key, user.pk)
    if not owned:
        raise StoryNotFoundError(f"Photo #{event_id} not found for user")
    return {"url": photo_storage.presign_get(photo.original_key)}


def list_active(user):
    """All currently-active Stories for the user, newest first."""
    return list(
        Story.objects.filter(user=user, stopped__isnull=True).order_by("-started")
    )


def list_history(user, page=1, page_size=20):
    """Paginated stopped Stories for the user, newest stop first.

    Returns ``(items, total_count)``.
    """
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    qs = Story.objects.filter(user=user, stopped__isnull=False).order_by("-stopped")
    total = qs.count()
    offset = (page - 1) * page_size
    items = list(qs[offset : offset + page_size])
    return items, total


def get_detail(user, story_id):
    """Story + list of JournalAdded events linked to it, newest first.

    HabitTracked rows that were attached as a side-effect of journal
    processing (e.g. POI extraction from ``#poi`` hashtags) are
    intentionally *not* included here — the JournalAdded already carries
    the same information in its comment, and the Android client prefers
    to derive map pins from there.
    """
    story = _get_owned_story(user, story_id)
    entries = (
        StoryEvent.objects.filter(story=story, event__journaladded__isnull=False)
        .select_related("event")
        .order_by("-event__published")
    )
    events = []
    for entry in entries:
        event = entry.event.get_real_instance()
        # PhotoAdded is-a JournalAdded, so it must be checked first.
        if isinstance(event, PhotoAdded):
            events.append(
                {
                    "id": event.pk,
                    "type": "photo",
                    "published": event.published,
                    "comment": event.comment,
                    "thumbnail_url": (
                        photo_storage.presign_get(event.thumbnail_key)
                        if event.thumbnail_key
                        else None
                    ),
                    "ready": event.thumbnail_key is not None,
                }
            )
        elif isinstance(event, JournalAdded):
            events.append(
                {
                    "id": event.pk,
                    "type": "journal",
                    "published": event.published,
                    "comment": event.comment,
                }
            )
    return story, events
