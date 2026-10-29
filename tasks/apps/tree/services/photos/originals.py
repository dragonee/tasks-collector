"""Access to a photo's full-resolution original, for trip and standalone photos.

Lives in the ``photos`` package rather than ``trips`` because it serves both:
the Android trip-photo and standalone-photo original endpoints share it.
"""

from ...models import PhotoAdded, StoryEvent
from . import storage as photo_storage
from .keys import photo_key_belongs_to


class PhotoNotFoundError(Exception):
    """No photo with the given id exists for this user."""


def presign_photo_original(user, event_id):
    """Fresh presigned GET URL for the full-resolution original of a photo the
    user owns.

    Ownership is resolved two ways so this serves both trip photos and
    standalone ones: a trip photo is owned if a ``StoryEvent`` links it to one
    of the user's Stories; a standalone photo (no ``StoryEvent``) is owned if
    its ``original_key`` lives under the user's ``photos/{user}/`` prefix (the
    Daily thread is global, so the key prefix is the only owner signal).

    Raises ``PhotoNotFoundError`` if no such owned photo exists (404-safe).
    """
    photo = PhotoAdded.objects.filter(pk=event_id).first()
    if photo is None:
        raise PhotoNotFoundError(f"Photo #{event_id} not found")
    entry = StoryEvent.objects.select_related("story").filter(event_id=event_id).first()
    if entry is not None:
        owned = entry.story.user_id == user.id
    else:
        owned = photo_key_belongs_to(photo.original_key, user.pk)
    if not owned:
        raise PhotoNotFoundError(f"Photo #{event_id} not found for user")
    return {"url": photo_storage.presign_get(photo.original_key)}
