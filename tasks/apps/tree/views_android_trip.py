from datetime import datetime as datetime_cls

from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.trips import (
    PhotoObjectMissingError,
    StoryNotFoundError,
    StoryStoppedError,
    add_trip_note,
    add_trip_photo,
    get_detail,
    list_active,
    list_history,
    presign_photo_original,
    presign_photo_upload,
    share_trip,
    start_trip,
    stop_trip,
    unshare_trip,
    update_trip,
)


def _bad_request(message):
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


def _not_found():
    return Response({"error": "story not found"}, status=status.HTTP_404_NOT_FOUND)


def _conflict(message):
    return Response({"error": message}, status=status.HTTP_409_CONFLICT)


def _parse_datetime(value):
    """Parse an ISO 8601 timestamp. Naive values are made tz-aware in the
    server's default timezone. Returns None on any failure.
    """
    if not value:
        return None
    text = str(value)
    if "T" not in text and " " not in text:
        return None
    try:
        parsed = datetime_cls.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _serialize_story(story):
    return {
        "id": story.pk,
        "type": story.type,
        "title": story.title,
        "started": story.started.isoformat(),
        "stopped": story.stopped.isoformat() if story.stopped else None,
    }


def _serialize_share(share, request):
    """Serialize a SharedStory with the full absolute public URL — the
    client never assembles URLs itself."""
    if share is None:
        return None
    return {
        "uuid": str(share.uuid),
        "url": request.build_absolute_uri(
            reverse("trip-shared-detail", args=[share.uuid])
        ),
    }


def _serialize_event(event):
    out = {
        "id": event["id"],
        "type": event["type"],
        "published": event["published"].isoformat(),
    }
    if event["type"] == "journal":
        out["comment"] = event["comment"]
    elif event["type"] == "photo":
        out["comment"] = event["comment"]
        out["thumbnail_url"] = event["thumbnail_url"]
        out["ready"] = event["ready"]
    elif event["type"] == "habit":
        out["habit_slug"] = event["habit_slug"]
        out["habit_name"] = event["habit_name"]
        out["occured"] = event["occured"]
        out["note"] = event["note"]
    return out


def _story_id_from(request):
    value = request.data.get("story_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripStartView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        title = request.data.get("title")
        if title is not None and not isinstance(title, str):
            return _bad_request("title must be a string")
        type_ = request.data.get("type") or "trip"
        if type_ not in {"trip"}:
            return _bad_request("invalid type")
        story = start_trip(request.user, title=title, type_=type_)
        return Response({"story": _serialize_story(story)}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripStopView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        story_id = _story_id_from(request)
        if story_id is None:
            return _bad_request("story_id is required")
        try:
            story = stop_trip(request.user, story_id)
        except StoryNotFoundError:
            return _not_found()
        return Response({"story": _serialize_story(story)}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripUpdateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        story_id = _story_id_from(request)
        if story_id is None:
            return _bad_request("story_id is required")
        title = request.data.get("title")
        if title is None or not isinstance(title, str) or not title.strip():
            return _bad_request("title is required")
        try:
            story = update_trip(request.user, story_id, title=title)
        except StoryNotFoundError:
            return _not_found()
        return Response({"story": _serialize_story(story)}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripShareView(APIView):
    """Create-or-get the public share link for a trip (stopped trips too)."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        story_id = _story_id_from(request)
        if story_id is None:
            return _bad_request("story_id is required")
        try:
            share = share_trip(request.user, story_id)
        except StoryNotFoundError:
            return _not_found()
        return Response(
            {"shared": True, "share": _serialize_share(share, request)},
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripShareRevokeView(APIView):
    """Delete the share link. Idempotent: revoking an unshared trip is 200."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        story_id = _story_id_from(request)
        if story_id is None:
            return _bad_request("story_id is required")
        try:
            unshare_trip(request.user, story_id)
        except StoryNotFoundError:
            return _not_found()
        return Response({"shared": False, "share": None}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripNoteView(APIView):
    """Add a journal note to an active trip.

    The ``comment`` is fed through ``process_journal_entry`` so any
    ``#poi``/``#coords``/``#coordinates``/``#latlng`` hashtag inside it
    also creates a ``HabitTracked``; both the ``JournalAdded`` itself
    and any extracted ``HabitTracked`` are linked to the story via
    ``StoryEvent``.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        story_id = _story_id_from(request)
        if story_id is None:
            return _bad_request("story_id is required")
        comment = request.data.get("comment")
        if not isinstance(comment, str) or not comment.strip():
            return _bad_request("comment is required")
        published = _parse_datetime(request.data.get("published"))
        if published is None:
            return _bad_request("published is required (full ISO 8601 timestamp)")
        idempotency_key = request.data.get("idempotency_key")
        if idempotency_key is not None and not isinstance(idempotency_key, str):
            return _bad_request("idempotency_key must be a string")
        try:
            journal = add_trip_note(
                request.user,
                story_id,
                comment=comment,
                published=published,
                idempotency_key=idempotency_key,
            )
        except StoryNotFoundError:
            return _not_found()
        except StoryStoppedError:
            return _conflict("trip is stopped; cannot add notes")
        return Response(
            {"ok": True, "journal_id": journal.pk}, status=status.HTTP_200_OK
        )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            page = int(request.query_params.get("page", "1"))
            page_size = int(request.query_params.get("page_size", "20"))
        except (TypeError, ValueError):
            return _bad_request("page and page_size must be integers")
        active = list_active(request.user)
        history, total = list_history(request.user, page=page, page_size=page_size)
        return Response(
            {
                "active": [_serialize_story(s) for s in active],
                "history": [_serialize_story(s) for s in history],
                "total_history": total,
                "page": page,
                "page_size": page_size,
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, story_id):
        try:
            story, events = get_detail(request.user, story_id)
        except StoryNotFoundError:
            return _not_found()
        return Response(
            {
                "story": _serialize_story(story),
                "events": [_serialize_event(e) for e in events],
                "share": _serialize_share(getattr(story, "share", None), request),
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripPhotoPresignView(APIView):
    """Allocate an S3 key and return a presigned PUT URL for a photo upload.

    The device uploads the original bytes directly to S3 with the returned
    ``upload_url`` (an unauthenticated PUT), then calls the confirm endpoint.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        story_id = _story_id_from(request)
        if story_id is None:
            return _bad_request("story_id is required")
        content_type = request.data.get("content_type")
        if not isinstance(content_type, str) or not content_type.strip():
            return _bad_request("content_type is required")
        try:
            result = presign_photo_upload(
                request.user, story_id, content_type=content_type
            )
        except StoryNotFoundError:
            return _not_found()
        except StoryStoppedError:
            return _conflict("trip is stopped; cannot add photos")
        except ValueError as e:
            return _bad_request(str(e))
        return Response(result, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripPhotoConfirmView(APIView):
    """Confirm an uploaded photo and create the PhotoAdded event.

    Like ``AndroidTripNoteView``, the ``comment`` runs through
    ``process_journal_entry`` so a ``#poi`` line still creates a HabitTracked.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        story_id = _story_id_from(request)
        if story_id is None:
            return _bad_request("story_id is required")
        key = request.data.get("key")
        if not isinstance(key, str) or not key.strip():
            return _bad_request("key is required")
        content_type = request.data.get("content_type")
        if not isinstance(content_type, str) or not content_type.strip():
            return _bad_request("content_type is required")
        comment = request.data.get("comment")
        if not isinstance(comment, str):
            return _bad_request("comment is required")
        published = _parse_datetime(request.data.get("published"))
        if published is None:
            return _bad_request("published is required (full ISO 8601 timestamp)")
        idempotency_key = request.data.get("idempotency_key")
        if idempotency_key is not None and not isinstance(idempotency_key, str):
            return _bad_request("idempotency_key must be a string")
        try:
            photo = add_trip_photo(
                request.user,
                story_id,
                key=key,
                comment=comment,
                content_type=content_type,
                published=published,
                idempotency_key=idempotency_key,
            )
        except StoryNotFoundError:
            return _not_found()
        except StoryStoppedError:
            return _conflict("trip is stopped; cannot add photos")
        except PhotoObjectMissingError:
            return _conflict("uploaded photo not found; re-upload and retry")
        return Response({"ok": True, "photo_id": photo.pk}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTripPhotoOriginalView(APIView):
    """Return a fresh short-lived presigned GET URL for a photo's original."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, event_id):
        try:
            result = presign_photo_original(request.user, event_id)
        except StoryNotFoundError:
            return _not_found()
        return Response(result, status=status.HTTP_200_OK)
