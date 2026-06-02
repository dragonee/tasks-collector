from datetime import date as date_cls
from datetime import datetime as datetime_cls

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.today import (
    NoBoardError,
    add_task,
    delete_task,
    list_board_items,
    list_today_tasks,
    set_task_done,
)


def _text_from(request):
    text = request.data.get("text") if hasattr(request, "data") else None
    if text is None or not str(text).strip():
        return None
    return str(text)


def _parse_date(value):
    """Parse a YYYY-MM-DD string. Returns the date or None on any failure."""
    if not value:
        return None
    try:
        return date_cls.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_datetime(value):
    """Parse an ISO 8601 timestamp (e.g. ``2026-05-21T15:42:33+02:00``).

    Returns a timezone-aware datetime, or None on any failure. Date-only
    inputs are rejected so callers can require the full timestamp on
    ``/complete``. Naive datetimes are made aware in the server's default
    timezone.
    """
    if not value:
        return None
    text = str(value)
    if "T" not in text and " " not in text:
        # Reject date-only strings — the contract here is a full timestamp.
        return None
    try:
        parsed = datetime_cls.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _bad_request(message):
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


def _no_board_response():
    return Response(
        {"error": "no board configured for user"},
        status=status.HTTP_409_CONFLICT,
    )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTaskListView(APIView):
    """Return today's tasks: every line in today's Plan.focus, with a
    ``done`` flag for those that also appear in today's Reflection.good.
    Unchecked items first.

    ``date`` query parameter is required (YYYY-MM-DD) — the client sends
    the device's local date so the call follows the user's day regardless
    of the server's timezone.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = _parse_date(request.query_params.get("date"))
        if today is None:
            return _bad_request("date is required (YYYY-MM-DD)")
        try:
            items = list_today_tasks(request.user, today=today)
        except NoBoardError:
            return _no_board_response()
        return Response(
            {"items": [{"text": it.text, "done": it.done} for it in items]},
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidBoardListView(APIView):
    """Return the user's current board flattened to a depth-annotated list:
    every node in pre-order, with its MoSCoW marker and done flag. Source for
    the Android 'add from board' picker. The board is date-independent, so no
    ``date`` parameter is required.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            items = list_board_items(request.user)
        except NoBoardError:
            return _no_board_response()
        return Response(
            {
                "items": [
                    {
                        "text": it.text,
                        "moscow": it.moscow,
                        "depth": it.depth,
                        "done": it.done,
                    }
                    for it in items
                ]
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTaskAddView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = _text_from(request)
        if text is None:
            return _bad_request("text is required")
        today = _parse_date(request.data.get("date"))
        if today is None:
            return _bad_request("date is required (YYYY-MM-DD)")
        try:
            add_task(request.user, text, today=today)
        except NoBoardError:
            return _no_board_response()
        return Response({"ok": True}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTaskCompleteView(APIView):
    """Set the desired done-state of a task. ``done`` is required and is
    the target state (not a toggle).

    The ``date`` field carries a full ISO 8601 timestamp (with offset, to
    second precision or better) — the device's wall-clock moment of the
    tap. The server uses it both to derive the day for Plan / Reflection
    writes and as the ``published`` time of any ``JournalAdded`` recorded
    for this completion. An optional ``note`` field captures free-form
    text from the journal-note modal; when present, a ``JournalAdded``
    line ``[x] <post-tick text>`` (plus the note on subsequent lines) is
    created. Empty-string notes are kept (just the marker line). Missing
    ``note`` means no journal entry.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = _text_from(request)
        if text is None:
            return _bad_request("text is required")
        if "done" not in request.data:
            return _bad_request("done is required")
        published = _parse_datetime(request.data.get("date"))
        if published is None:
            return _bad_request("date is required (full ISO 8601 timestamp)")
        note = request.data.get("note")
        if note is not None and not isinstance(note, str):
            return _bad_request("note must be a string")
        done = bool(request.data.get("done"))
        try:
            set_task_done(request.user, text, done, published=published, note=note)
        except NoBoardError:
            return _no_board_response()
        return Response({"ok": True}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTaskDeleteView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = _text_from(request)
        if text is None:
            return _bad_request("text is required")
        today = _parse_date(request.data.get("date"))
        if today is None:
            return _bad_request("date is required (YYYY-MM-DD)")
        try:
            delete_task(request.user, text, today=today)
        except NoBoardError:
            return _no_board_response()
        return Response({"ok": True}, status=status.HTTP_200_OK)
