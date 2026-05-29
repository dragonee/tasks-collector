"""Pure helpers for trip-photo S3 key naming and content-type validation."""

import uuid

# Allowed upload content types -> file extension for the original object.
CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def ext_for_content_type(content_type):
    """Return the file extension for an allowed content type.

    Raises ``ValueError`` for unsupported types.
    """
    try:
        return CONTENT_TYPE_EXT[content_type]
    except KeyError as e:
        raise ValueError(f"unsupported content type: {content_type!r}") from e


def original_key(user_id, story_id, content_type):
    """Allocate a fresh S3 key for an original photo upload."""
    ext = ext_for_content_type(content_type)
    return f"trips/{user_id}/{story_id}/{uuid.uuid4()}.{ext}"


def thumbnail_key_for(original):
    """Deterministic WebP thumbnail key derived from an original key."""
    base = original.rsplit(".", 1)[0]
    return f"{base}_thumb.webp"


def key_belongs_to(key, user_id, story_id):
    """Guard: a confirmed key must live under this user's/story's prefix."""
    return key.startswith(f"trips/{user_id}/{story_id}/")
