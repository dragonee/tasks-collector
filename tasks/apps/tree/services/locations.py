"""Where an event happened (``EventLocation``).

A phone sends a place as fields of the note or photo it writes: ``lat``,
``lng`` and, when it knows how far off it may be, ``acc`` in metres. Phones
from before that wrote it as the comment's first line, ``#poi lat=… lng=…``
(the tag may also be #coords, #coordinates or #latlng); ``split_place`` reads
that line off for as long as one of those phones may still send it.
"""

import math
import re
from collections import namedtuple

from ..models import EventLocation

Place = namedtuple("Place", "lat lng acc")

PLACE_LINE = re.compile(
    r"\A[ \t]*#(?:poi|coords|coordinates|latlng)\b"
    r"[^\n]*?\blat\s*=\s*(-?\d+(?:\.\d+)?)"
    r"[^\n]*?\blng\s*=\s*(-?\d+(?:\.\d+)?)"
    r"(?:[^\n]*?\bacc\s*=\s*(\d+(?:\.\d+)?))?"
    r"[^\n]*(?:\n|\Z)",
    re.IGNORECASE,
)


def split_place(comment):
    """``comment`` without a leading place line, and the place it named (a
    ``Place``), or ``comment`` as it is and None."""
    match = PLACE_LINE.match(comment or "")
    if match is None:
        return comment, None
    lat, lng, acc = match.groups()
    place = _checked(float(lat), float(lng), float(acc) if acc else None)
    if place is None:
        return comment, None
    return comment[match.end() :], place


def place_from(data):
    """The place a request's ``lat``, ``lng`` and ``acc`` name, or None when it
    names none. Raises ValueError for one that is no place on Earth."""
    lat, lng, acc = data.get("lat"), data.get("lng"), data.get("acc")
    if lat is None and lng is None:
        return None
    try:
        place = _checked(
            float(lat), float(lng), float(acc) if acc is not None else None
        )
    except TypeError, ValueError:
        place = None
    if place is None:
        raise ValueError(
            "lat and lng must be numbers, -90..90 and -180..180; acc metres"
        )
    return place


def _checked(lat, lng, acc):
    numbers = [lat, lng] + ([acc] if acc is not None else [])
    if not all(math.isfinite(n) for n in numbers):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (acc is not None and acc < 0):
        return None
    return Place(lat, lng, acc)


def locate(event, place):
    """Give ``event`` the ``place`` it happened at (none when it is None)."""
    if place is not None:
        EventLocation.objects.update_or_create(
            event=event,
            defaults={"lat": place.lat, "lng": place.lng, "acc": place.acc},
        )


def location_of(event):
    """``event``'s location, or None."""
    try:
        return event.location
    except EventLocation.DoesNotExist:
        return None
