from django.http import JsonResponse

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ApiToken


def health_check(request):
    """Health check endpoint for Docker container health monitoring."""
    return JsonResponse({"status": "healthy"})


@api_view(["GET"])
def me(request):
    """Who the caller is logged in as, and with what: the token's name and
    whether it can only read, or null for a password or a session.
    ``tc whoami`` asks this."""
    token = request.auth if isinstance(request.auth, ApiToken) else None
    return Response(
        {
            "username": request.user.username,
            "token": (
                None
                if token is None
                else {"name": token.name, "read_only": token.read_only}
            ),
        }
    )
