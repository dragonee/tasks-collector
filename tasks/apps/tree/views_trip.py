"""Web (HTML) views for Trips (Story).

The Android client drives trips through the JSON API in
``views_android_trip``; these views are the human-facing mirror — an index
of the user's trips, a per-trip page that reuses the journal-entry partial
to render notes and photo miniatures, the HTMX share/unshare toggle, and
the public (unauthenticated) page behind a share link.

The owner of an *active* trip can also attach notes and photos here: the
write views reuse the same ``services.trips`` operations the Android API does
(session auth + CSRF instead of token auth), so no logic is duplicated. Photos
take the same presign -> direct-to-storage PUT -> confirm path, but signed for
a browser (``web=True``) rather than the device-facing endpoint.
"""

import json
import re

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

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


def _story_events(story):
    """All journal/photo entries of a trip as real model instances, newest
    first, with presigned photo URLs attached.

    Mirrors ``operations.get_detail`` (JournalAdded + PhotoAdded, no
    side-effect HabitTracked rows). Shared by the private and public detail
    views so both render through the same pipeline.
    """
    entries = (
        StoryEvent.objects.filter(story=story, event__journaladded__isnull=False)
        .select_related("event")
        .order_by("-event__published")
    )
    events = [entry.event.get_real_instance() for entry in entries]
    return attach_photo_urls(events)


def _share_context(request, story):
    share = getattr(story, "share", None)
    share_url = (
        request.build_absolute_uri(reverse("trip-shared-detail", args=[share.uuid]))
        if share
        else None
    )
    return {"story": story, "share": share, "share_url": share_url}


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


def _detail_context(request, story):
    """Full render context for the private trip-detail page (and for re-rendering
    after a note/photo write).

    ``can_add`` gates the owner-only "add to trip" panel and its JS: only the
    owner of an *active* trip may attach notes/photos (the service layer rejects
    writes to a stopped trip anyway). The public shared view builds its own
    context without these flags, so the panel never appears there.
    """
    events = _story_events(story)
    return {
        **_share_context(request, story),
        "events": events,
        "map_points": _map_points(events),
        "show_share_control": True,
        "can_add": story.stopped is None,
    }


def _owned_story_or_404(request, story_id):
    story = Story.objects.filter(pk=story_id, user=request.user).first()
    if story is None:
        raise Http404("Trip not found")
    return story


def _render_entries(request, story_id):
    """Re-render the timeline partial after a write so HTMX can swap it in."""
    story = _owned_story_or_404(request, story_id)
    return render(
        request,
        "tree/trips/_trip_entries.html",
        {"events": _story_events(story), "can_add": story.stopped is None},
    )


@login_required
def trip_detail(request, story_id):
    """A single trip with all its journal/photo entries, newest first.

    Mirrors ``operations.get_detail`` (JournalAdded + PhotoAdded, no
    side-effect HabitTracked rows) but returns real model instances so the
    journal partial can render them.
    """
    story = _owned_story_or_404(request, story_id)
    return render(
        request, "tree/trips/trip_detail.html", _detail_context(request, story)
    )


@login_required
@require_POST
def trip_share(request, story_id):
    """HTMX endpoint: create the public share link and re-render the share
    control with the URL + Unshare button."""
    try:
        share = trip_ops.share_trip(request.user, story_id)
    except trip_ops.StoryNotFoundError:
        raise Http404("Trip not found")
    return render(
        request,
        "tree/trips/_share_control.html",
        _share_context(request, share.story),
    )


@login_required
@require_POST
def trip_unshare(request, story_id):
    """HTMX endpoint: revoke the share link and re-render the share control."""
    try:
        story = trip_ops.unshare_trip(request.user, story_id)
    except trip_ops.StoryNotFoundError:
        raise Http404("Trip not found")
    return render(
        request,
        "tree/trips/_share_control.html",
        _share_context(request, story),
    )


@login_required
@require_POST
def trip_add_note(request, story_id):
    """Attach a text note to a trip and re-render the timeline for an HTMX swap.

    Session-auth web twin of ``AndroidTripNoteView``: both call
    ``operations.add_trip_note``. CSRF rides in the form field (the same
    mechanism the share toggle uses).
    """
    comment = (request.POST.get("comment") or "").strip()
    if not comment:
        return HttpResponseBadRequest("comment is required")
    try:
        trip_ops.add_trip_note(
            request.user, story_id, comment, published=timezone.now()
        )
    except trip_ops.StoryNotFoundError:
        raise Http404("Trip not found")
    except trip_ops.StoryStoppedError:
        return HttpResponse(status=409)
    return _render_entries(request, story_id)


@login_required
@require_POST
def trip_photo_presign(request, story_id):
    """Allocate an S3 key and return a browser-reachable presigned PUT URL.

    Session-auth web twin of ``AndroidTripPhotoPresignView`` — but signs the
    *web* endpoint (``web=True``) so the browser can PUT directly to the bucket.
    """
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponseBadRequest("invalid JSON")
    content_type = (payload.get("content_type") or "").strip()
    if not content_type:
        return HttpResponseBadRequest("content_type is required")
    try:
        result = trip_ops.presign_photo_upload(
            request.user, story_id, content_type, web=True
        )
    except trip_ops.StoryNotFoundError:
        raise Http404("Trip not found")
    except trip_ops.StoryStoppedError:
        return HttpResponse(status=409)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))
    return JsonResponse(result)


@login_required
@require_POST
def trip_photo_confirm(request, story_id):
    """Confirm a browser-uploaded photo and re-render the timeline.

    Session-auth web twin of ``AndroidTripPhotoConfirmView``: both call
    ``operations.add_trip_photo``, which links the PhotoAdded to the story and
    enqueues the thumbnail task. Returns the timeline partial so the new photo
    shows immediately (original first; the WebP thumbnail swaps in later).
    """
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponseBadRequest("invalid JSON")
    key = (payload.get("key") or "").strip()
    content_type = (payload.get("content_type") or "").strip()
    comment = payload.get("comment") or ""
    if not key or not content_type:
        return HttpResponseBadRequest("key and content_type are required")
    try:
        trip_ops.add_trip_photo(
            request.user,
            story_id,
            key,
            comment,
            content_type,
            published=timezone.now(),
        )
    except trip_ops.StoryNotFoundError:
        raise Http404("Trip not found")
    except trip_ops.StoryStoppedError:
        return HttpResponse(status=409)
    except trip_ops.PhotoObjectMissingError:
        return HttpResponseBadRequest("uploaded object not found")
    return _render_entries(request, story_id)


def trip_shared_detail(request, share_uuid):
    """Public, unauthenticated mirror of ``trip_detail``, keyed by share UUID."""
    share = trip_ops.get_shared_story(share_uuid)
    if share is None:
        raise Http404("Shared trip not found")

    story = share.story
    events = _story_events(story)

    return render(
        request,
        "tree/trips/trip_shared_detail.html",
        {
            "story": story,
            "events": events,
            "map_points": _map_points(events),
        },
    )
