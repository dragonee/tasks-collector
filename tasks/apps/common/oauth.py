"""Logging a device in: OAuth 2.0 authorization code with PKCE.

An app that wants to act as a user (the phone) doesn't ask for their
password. It opens ``oauth/authorize/`` in the browser, where the user logs
in the way they always do and says yes; the browser is sent back to the app
with a code, and the app trades the code for a token of its own at
``oauth/token/``. The token is an ``ApiToken``: it doesn't expire, and the
user revokes it from their account settings (the app, with
``oauth/revoke/``).

The app is a public client (RFC 8252): it has no secret. What ties the code
to the app that asked for it is PKCE (RFC 7636): the app sends the hash of
a random verifier with the request and the verifier itself with the code.
Which apps may ask, and where their answers may be sent, is
``settings.OAUTH_CLIENTS``.
"""

import base64
import hashlib
import re
import secrets
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .models import ApiToken, AuthorizationCode

# An S256 challenge is 32 bytes in base64url without padding; a verifier is
# 43 to 128 characters of the unreserved set.
CHALLENGE_RE = re.compile(r"[A-Za-z0-9_-]{43}")
VERIFIER_RE = re.compile(r"[A-Za-z0-9._~-]{43,128}")


class ClientRedirect(HttpResponseRedirect):
    """The answer to an authorization request, sent to the client's
    redirect URI. That URI is one registered for the client, so its scheme
    (an app's own) is allowed."""

    def __init__(self, redirect_uri, **params):
        self.allowed_schemes = [urlsplit(redirect_uri).scheme]
        query = urlencode({key: value for key, value in params.items() if value})
        separator = "&" if "?" in redirect_uri else "?"
        super().__init__(f"{redirect_uri}{separator}{query}")


def _token_name(client, device_name):
    return f"{client['name']} on {device_name}" if device_name else client["name"]


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def authorize(request):
    """Ask the user whether the client may have a token, and send the
    client their answer.

    The request is in the query string (``response_type=code``,
    ``client_id``, ``redirect_uri``, ``code_challenge``,
    ``code_challenge_method=S256``, ``state``, and ``device_name`` to tell
    one phone from another); the page posts back to the same URL.
    """
    asked = request.GET
    client = settings.OAUTH_CLIENTS.get(asked.get("client_id", ""))
    redirect_uri = asked.get("redirect_uri", "")
    if client is None or redirect_uri not in client["redirect_uris"]:
        # Nowhere it would be safe to send an answer: say so here.
        return render(request, "registration/authorize.html", status=400)

    state = asked.get("state", "")
    if asked.get("response_type") != "code":
        return ClientRedirect(
            redirect_uri, error="unsupported_response_type", state=state
        )
    challenge = asked.get("code_challenge", "")
    with_s256 = asked.get("code_challenge_method") == "S256"
    if not with_s256 or not CHALLENGE_RE.fullmatch(challenge):
        return ClientRedirect(
            redirect_uri,
            error="invalid_request",
            error_description="code_challenge with S256 is required",
            state=state,
        )
    device_name = asked.get("device_name", "").strip()[:100]

    if request.method == "POST":
        if "allow" not in request.POST:
            return ClientRedirect(redirect_uri, error="access_denied", state=state)
        code = AuthorizationCode.objects.issue(
            request.user, asked["client_id"], redirect_uri, challenge, device_name
        )
        return ClientRedirect(redirect_uri, code=code, state=state)

    return render(
        request,
        "registration/authorize.html",
        {"client": client, "token_name": _token_name(client, device_name)},
    )


def _refused(error, status=400):
    return JsonResponse({"error": error}, status=status)


def _verifies(challenge, verifier):
    if not VERIFIER_RE.fullmatch(verifier):
        return False
    hashed = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(hashed).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, challenge)


@csrf_exempt
@require_POST
def token(request):
    """Trade an authorization code for a token (form-encoded:
    ``grant_type=authorization_code``, ``code``, ``code_verifier``,
    ``client_id``, ``redirect_uri``). Answers ``{"access_token",
    "token_type": "Token"}``: the key to send as ``Authorization: Token``.
    """
    sent = request.POST
    if sent.get("grant_type") != "authorization_code":
        return _refused("unsupported_grant_type")

    # Used up whatever comes next: a code is good for one try.
    code = AuthorizationCode.objects.redeem(sent.get("code", ""))
    if (
        code is None
        or code.client_id != sent.get("client_id")
        or code.redirect_uri != sent.get("redirect_uri")
        or not _verifies(code.code_challenge, sent.get("code_verifier", ""))
        or not code.user.is_active
    ):
        return _refused("invalid_grant")

    client = settings.OAUTH_CLIENTS.get(code.client_id)
    if client is None:
        return _refused("invalid_client", status=401)

    _token, key = ApiToken.objects.issue(
        code.user, _token_name(client, code.device_name)
    )
    response = JsonResponse({"access_token": key, "token_type": "Token"})
    response["Cache-Control"] = "no-store"
    return response


@csrf_exempt
@require_POST
def revoke(request):
    """Revoke the token sent as ``token`` (RFC 7009): an app logging out.
    Having the token is what it takes; an unknown one is fine too."""
    found = ApiToken.objects.for_key(request.POST.get("token", ""))
    if found is not None:
        found.delete()
    return JsonResponse({})


@login_required
@require_POST
def revoke_token(request, pk):
    """Revoke one of the caller's tokens, from their account settings."""
    found = get_object_or_404(ApiToken, pk=pk, user=request.user)
    found.delete()
    messages.success(request, f"{found.name} is logged out.")
    return redirect("account-settings")
