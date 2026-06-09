"""Android endpoints for standalone (storyless) photos.

The capture flow mirrors the trip-photo one — presign an S3 key, the device
PUTs the bytes directly, then confirms — but there is no Story: a confirm
creates a ``PhotoAdded`` on the Daily thread linked to no trip. The original
endpoint is shared with trips via the generalized ``presign_photo_original``.
"""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.photos import (
    PhotoObjectMissingError,
    add_standalone_photo,
    presign_standalone_photo,
)
from .views_android_trip import _bad_request, _conflict, _parse_datetime


@method_decorator(csrf_exempt, name="dispatch")
class AndroidPhotoPresignView(APIView):
    """Allocate an S3 key and return a presigned PUT URL for a storyless photo.

    The device uploads the original bytes directly to S3 with the returned
    ``upload_url`` (an unauthenticated PUT), then calls the confirm endpoint.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        content_type = request.data.get("content_type")
        if not isinstance(content_type, str) or not content_type.strip():
            return _bad_request("content_type is required")
        try:
            result = presign_standalone_photo(request.user, content_type=content_type)
        except ValueError as e:
            return _bad_request(str(e))
        return Response(result, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidPhotoConfirmView(APIView):
    """Confirm an uploaded storyless photo and create the PhotoAdded event.

    Like the trip-photo confirm, ``comment`` runs through
    ``process_journal_entry`` so a ``#poi`` line still creates a HabitTracked.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
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
            photo = add_standalone_photo(
                request.user,
                key=key,
                comment=comment,
                content_type=content_type,
                published=published,
                idempotency_key=idempotency_key,
            )
        except PhotoObjectMissingError:
            return _conflict("uploaded photo not found; re-upload and retry")
        return Response({"ok": True, "photo_id": photo.pk}, status=status.HTTP_200_OK)
