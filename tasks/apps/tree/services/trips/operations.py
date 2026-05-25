"""Orchestrated Trip (Story) operations.

Each public mutator is wrapped in ``transaction.atomic`` so multi-record
writes (Story + JournalAdded + StoryEvent + possibly HabitTracked)
either all commit or none do.
"""

from django.db import transaction
from django.utils import timezone

from ...models import JournalAdded, Profile, Story, StoryEvent, Thread
from ..journalling import process_journal_entry
from .titles import default_title


class StoryNotFoundError(Exception):
    """No Story with the given id exists for this user."""


class StoryStoppedError(Exception):
    """The Story is already stopped; no further events can be attached."""


def _daily_thread():
    return Thread.objects.get(name="Daily")


def _journal_thread_for(user):
    """Resolve the Thread used for a trip note's JournalAdded.

    Mirrors the Today flow: prefer ``Profile.default_board_thread``,
    fall back to the Daily thread so the operation never silently
    no-ops on users without a configured default.
    """
    try:
        profile = Profile.objects.select_related("default_board_thread").get(user=user)
    except Profile.DoesNotExist:
        return _daily_thread()
    if profile.default_board_thread is not None:
        return profile.default_board_thread
    return _daily_thread()


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
def add_trip_note(user, story_id, comment, published=None):
    """Create a JournalAdded linked to ``story``, processed through the
    journalling pipeline so embedded hashtags create HabitTracked
    entries that are also linked to the story.

    Raises ``StoryStoppedError`` if the story is already stopped.
    """
    story = _get_owned_story(user, story_id)
    if story.stopped is not None:
        raise StoryStoppedError(f"Story #{story_id} is stopped; cannot add new notes.")

    journal_added = JournalAdded.objects.create(
        thread=_journal_thread_for(user),
        comment=comment,
        published=published or timezone.now(),
    )
    process_journal_entry(journal_added, story=story)
    return journal_added


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
        if not isinstance(event, JournalAdded):
            continue
        events.append(
            {
                "id": event.pk,
                "type": "journal",
                "published": event.published,
                "comment": event.comment,
            }
        )
    return story, events
