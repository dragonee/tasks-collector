"""Sharing a trip, observation or projected outcome with other users."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .services.streams import (
    SharingError,
    owned_shareable_stream,
    revoke,
    share,
    viewers,
)


def sharing_context(request, stream, error=None):
    """Context for ``tree/_stream_sharing.html``: who ``stream`` is shared
    with and the form to change it. Empty unless the user owns the stream and
    it can be shared, so the panel only shows to its owner."""
    if stream is None or owned_shareable_stream(request.user, stream.pk) is None:
        return {}
    return {
        "sharing": {
            "stream": stream,
            "viewers": viewers(stream),
            "next": request.get_full_path(),
            "error": error,
        }
    }


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

    action = request.POST.get("action")
    username = request.POST.get("username", "").strip()
    if action not in ("share", "revoke") or not username:
        return HttpResponseBadRequest("action and username are required")

    error = None
    try:
        (share if action == "share" else revoke)(request.user, stream, username)
    except SharingError as e:
        error = str(e)

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
