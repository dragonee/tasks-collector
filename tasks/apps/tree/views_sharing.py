"""Sharing a trip, observation, projected outcome or board with other users."""

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response as RestResponse

from .models import EventStreamAccess, Thread
from .services.streams import (
    SharingError,
    owned_shareable_stream,
    revoke,
    share,
    share_role,
    shared_with,
)


def _panel(request, stream, users, error=None):
    return {
        "stream": stream,
        "viewers": users,
        "role": share_role(stream),
        "next": request.get_full_path(),
        "error": error,
    }


def sharing_context(request, stream, error=None):
    """Context for ``tree/_stream_sharing.html``: who ``stream`` is shared
    with and the form to change it. Empty unless the user owns the stream and
    it can be shared, so the panel only shows to its owner."""
    if stream is None or owned_shareable_stream(request.user, stream.pk) is None:
        return {}
    return {"sharing": _panel(request, stream, shared_with(stream), error)}


def board_sharing_panels(request):
    """A sharing panel for each of the user's boards that can be shared (all
    but the built-in ones), as ``[{"thread": ..., "sharing": ...}]``."""
    threads = list(
        Thread.objects.for_user(request.user)
        .exclude(name__in=Thread.BUILTIN_NAMES)
        .select_related("board_stream")
    )
    editors = defaultdict(list)
    accesses = (
        EventStreamAccess.objects.filter(
            stream__in=[thread.board_stream_id for thread in threads],
            role=EventStreamAccess.Role.EDITOR,
        )
        .select_related("user")
        .order_by("user__username")
    )
    for access in accesses:
        editors[access.stream_id].append(access.user)
    return [
        {
            "thread": thread,
            "sharing": _panel(
                request, thread.board_stream, editors[thread.board_stream_id]
            ),
        }
        for thread in threads
    ]


def _share_or_revoke(owner, stream, data):
    """Apply ``data``'s ``action`` ("share" or "revoke") for its ``username``.
    Returns ``(error, bad_request)``: why the share or revoke couldn't be
    done, and whether the request itself was malformed."""
    if not isinstance(data, dict):
        return None, True
    action = data.get("action")
    username = data.get("username")
    if (
        action not in ("share", "revoke")
        or not isinstance(username, str)
        or not username.strip()
    ):
        return None, True
    try:
        (share if action == "share" else revoke)(owner, stream, username.strip())
    except SharingError as e:
        return str(e), False
    return None, False


@api_view(["GET", "POST"])
def stream_sharing_api(request, stream_id):
    """A stream's sharing as JSON, for the board page: who it is shared with
    and the access sharing gives. POST ``{"action": "share" | "revoke",
    "username": ...}`` changes it. A share that can't be done (an unknown
    username, yourself) still answers 200, with the reason in ``error``, as
    the HTML panel shows it."""
    stream = owned_shareable_stream(request.user, stream_id)
    if stream is None:
        raise Http404

    error = None
    if request.method == "POST":
        error, bad_request = _share_or_revoke(request.user, stream, request.data)
        if bad_request:
            return RestResponse(
                {"error": "action and username are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    return RestResponse(
        {
            "stream": str(stream.pk),
            "role": share_role(stream),
            "shared_with": [user.username for user in shared_with(stream)],
            "error": error,
        }
    )


@login_required
@require_POST
def stream_sharing(request, stream_id):
    """Share the stream with, or stop sharing it with, a user by username.

    Answers HTMX with the re-rendered sharing panel (showing any error);
    otherwise goes back to the page the form was on.
    """
    stream = owned_shareable_stream(request.user, stream_id)
    if stream is None:
        raise Http404

    error, bad_request = _share_or_revoke(request.user, stream, request.POST)
    if bad_request:
        return HttpResponseBadRequest("action and username are required")

    if request.htmx:
        context = sharing_context(request, stream, error=error)
        context["sharing"]["next"] = request.POST.get("next", "")
        return render(request, "tree/_stream_sharing.html", context)

    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        next_url = "/"
    return redirect(next_url)
