"""Access to a photo's full-resolution original, for trip and standalone photos.

Lives in the ``photos`` package rather than ``trips`` because it serves both:
the Android trip-photo and standalone-photo original endpoints share it.
"""

from ...models import EventStreamAccess, PhotoAdded
from . import storage as photo_storage


class PhotoNotFoundError(Exception):
    """No photo with the given id exists for this user."""


def presign_photo_original(user, event_id):
    """Fresh presigned GET URL for the full-resolution original of a photo the
    user owns.

    A photo is owned by whoever owns its home stream: the journal of the
    Daily thread it was uploaded to, for trip and standalone photos alike.

    Raises ``PhotoNotFoundError`` if no such owned photo exists (404-safe).
    """
    photo = PhotoAdded.objects.filter(
        pk=event_id,
        event_stream__access__user=user,
        event_stream__access__role=EventStreamAccess.Role.OWNER,
    ).first()
    if photo is None:
        raise PhotoNotFoundError(f"Photo #{event_id} not found for user")
    return {"url": photo_storage.presign_get(photo.original_key)}
