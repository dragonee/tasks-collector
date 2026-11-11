from rest_framework import authentication, exceptions

from .models import ApiToken


class TokenAuthentication(authentication.TokenAuthentication):
    """``Authorization: Token <key>``, the key being that of one of the
    user's ``ApiToken``s."""

    def authenticate_credentials(self, key):
        token = ApiToken.objects.for_key(key)
        if token is None:
            raise exceptions.AuthenticationFailed("Invalid token.")
        if not token.user.is_active:
            raise exceptions.AuthenticationFailed("User inactive or deleted.")

        token.used()
        return (token.user, token)
