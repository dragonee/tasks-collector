from rest_framework import authentication, exceptions, permissions

from .models import ApiToken


def reads_only(request):
    """Whether ``request`` changes nothing: a GET, or a view that says it
    only looks whatever the method (``read_only_tokens = True``, a preview
    that is posted)."""
    if request.method in permissions.SAFE_METHODS:
        return True
    view = (getattr(request, "parser_context", None) or {}).get("view")
    return getattr(view, "read_only_tokens", False)


class TokenAuthentication(authentication.TokenAuthentication):
    """``Authorization: Token <key>``, the key being that of one of the
    user's ``ApiToken``s. A read-only token gets nothing that writes."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            _user, token = result
            if token.read_only and not reads_only(request):
                raise exceptions.PermissionDenied("This token can only read.")
        return result

    def authenticate_credentials(self, key):
        token = ApiToken.objects.for_key(key)
        if token is None:
            raise exceptions.AuthenticationFailed("Invalid token.")
        if not token.user.is_active:
            raise exceptions.AuthenticationFailed("User inactive or deleted.")

        token.used()
        return (token.user, token)
