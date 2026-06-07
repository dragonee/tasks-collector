"""Read-only web (HTML) views for Trips (Story).

The Android client drives trips through the JSON API in
``views_android_trip``; these views are the human-facing mirror — an index
of the user's trips and a per-trip page that reuses the journal-entry
partial to render notes and photo miniatures. Nothing here mutates state.
"""

import re

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.template.defaultfilters import date as date_filter

from .models import PhotoAdded, Story, StoryEvent
from .services.photos import storage as photo_storage
from .services.trips import operations as trip_ops

# Trip notes/photos prepend a machine line like "#poi lat=.. lng=..". This is
# the server-side twin of POI_LINE_RE in tasks/assets/app.js — keep the two in
# sync. We parse coordinates here (rather than scraping the rendered DOM) so the
# map gets clean data; app.js mutates that DOM to strip the same line.
POI_LINE_RE = re.compile(
    r"#(?:poi|coords|coordinates|latlng)\b"
    r"[^\n]*?\blat\s*=\s*(-?\d+(?:\.\d+)?)"
    r"[^\n]*?\blng\s*=\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


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


def _cover_photos_by_story(user):
    """Map of story_id -> latest PhotoAdded linked to it (the tile cover).

    One pass over the user's photo StoryEvents (newest first); the first row
    seen per story is its latest photo. PhotoAdded shares its pk with the base
    Event, so the StoryEvent.event_id keys straight into ``in_bulk``.
    """
    rows = (
        StoryEvent.objects.filter(
            story__user=user, event__journaladded__photoadded__isnull=False
        )
        .order_by("story_id", "-event__published")
        .values_list("story_id", "event_id")
    )
    latest = {}
    for story_id, event_id in rows:
        latest.setdefault(story_id, event_id)
    photos = PhotoAdded.objects.in_bulk(latest.values())
    return {sid: photos[eid] for sid, eid in latest.items() if eid in photos}


def _map_points(events):
    """POIs to plot on the trip map, one per event that carries coordinates.

    Each point is JSON-serialisable for ``json_script`` and carries enough to
    render a marker (photo miniature or note pin), a popup, and to cross-link
    the history list on the right via the event id. ``attach_photo_urls`` must
    have run first so photo events already have ``thumbnail_url``/``original_url``.
    """
    points = []
    for event in events:
        match = POI_LINE_RE.search(event.comment or "")
        if not match:
            continue

        # The machine "#poi ..." line is the first line; the user's note (if
        # any) is whatever follows it — mirrors app.js's DOM stripping.
        _, _, note = (event.comment or "").partition("\n")
        is_photo = bool(getattr(event, "is_photo", False))

        points.append(
            {
                "id": event.id,
                "lat": float(match.group(1)),
                "lng": float(match.group(2)),
                "is_photo": is_photo,
                "thumbnail_url": getattr(event, "thumbnail_url", None)
                or getattr(event, "original_url", None),
                "note": note.strip(),
                "date": date_filter(event.published, "d M Y"),
                "time": date_filter(event.published, "H:i"),
            }
        )
    return points


def _trip_date_label(story):
    """Human date(s) for a trip tile. A same-day or still-active trip shows a
    single date rather than repeating it as a range."""
    start = date_filter(story.started, "d M Y")
    if story.stopped is None or story.started.date() == story.stopped.date():
        return start
    return f"{start} – {date_filter(story.stopped, 'd M Y')}"


@login_required
def trip_list(request):
    """Index of the user's trips as tiles (cover photo + title + dates),
    grouped by month with a month archive sidebar like the diary."""
    trips = list(Story.objects.filter(user=request.user).order_by("-started"))
    months = Story.objects.filter(user=request.user).dates(
        "started", "month", order="DESC"
    )

    covers = _cover_photos_by_story(request.user)
    attach_photo_urls(list(covers.values()))
    for trip in trips:
        trip.cover_photo = covers.get(trip.id)
        trip.date_label = _trip_date_label(trip)

    return render(
        request,
        "tree/trips/trip_list.html",
        {
            "trips": trips,
            "months": months,
        },
    )


@login_required
def trip_detail(request, story_id):
    """A single trip with all its journal/photo entries, newest first.

    Mirrors ``operations.get_detail`` (JournalAdded + PhotoAdded, no
    side-effect HabitTracked rows) but returns real model instances so the
    journal partial can render them.
    """
    story = Story.objects.filter(pk=story_id, user=request.user).first()
    if story is None:
        raise Http404("Trip not found")

    entries = (
        StoryEvent.objects.filter(story=story, event__journaladded__isnull=False)
        .select_related("event")
        .order_by("-event__published")
    )
    events = [entry.event.get_real_instance() for entry in entries]
    attach_photo_urls(events)

    return render(
        request,
        "tree/trips/trip_detail.html",
        {
            "story": story,
            "events": events,
            "map_points": _map_points(events),
        },
    )
