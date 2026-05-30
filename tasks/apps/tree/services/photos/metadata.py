"""Read capture metadata (the time a photo was taken) from image bytes.

Trip photos should be timestamped with when they were *taken*, not when they
were uploaded. The Android client sends its best guess (the gallery's
DATE_TAKEN); on confirm the backend re-derives the timestamp from the
original's EXIF and overrides it when present, so EXIF DateTimeOriginal is the
authoritative source regardless of client.
"""

import io
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from PIL import Image

# EXIF tag numbers (see the EXIF spec).
_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 0x9003  # in the Exif sub-IFD: "YYYY:MM:DD HH:MM:SS"
_OFFSET_TIME_ORIGINAL = 0x9011  # in the Exif sub-IFD: "+02:00"
_DATETIME = 0x0132  # in the main IFD; fallback when no DateTimeOriginal


def _parse_offset(value):
    """Parse an EXIF offset string like ``+02:00`` into a tzinfo, or None."""
    if not value:
        return None
    text = str(value).strip()
    if len(text) < 6 or text[0] not in "+-":
        return None
    try:
        hours = int(text[1:3])
        minutes = int(text[4:6])
    except ValueError:
        return None
    delta = timedelta(hours=hours, minutes=minutes)
    return dt_timezone(delta if text[0] == "+" else -delta)


def read_capture_datetime(raw):
    """Return the tz-aware capture time from an image's EXIF, or None.

    Prefers DateTimeOriginal (with OffsetTimeOriginal when present), falling
    back to the main-IFD DateTime tag. When EXIF records no UTC offset, the
    naive value is interpreted in the server's default timezone. Any failure
    (non-image bytes, absent or malformed EXIF) returns None.
    """
    try:
        exif = Image.open(io.BytesIO(raw)).getexif()
    except Exception:  # noqa: BLE001 - a bad image must never raise here
        return None
    if not exif:
        return None

    try:
        sub = exif.get_ifd(_EXIF_IFD)
    except Exception:  # noqa: BLE001
        sub = {}

    dt_str = (sub or {}).get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
    if not dt_str:
        return None

    try:
        naive = datetime.strptime(str(dt_str).strip(), "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None

    tz = _parse_offset((sub or {}).get(_OFFSET_TIME_ORIGINAL))
    if tz is not None:
        return naive.replace(tzinfo=tz)
    return timezone.make_aware(naive)
