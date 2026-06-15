"""
Health data helpers for the Android Health screen.

Body weight is recorded as a HabitTracked under a dedicated ``weight`` Habit
(see migration 0074). It is intentionally a separate Habit from
``health-metrics`` so the hourly background sync — which upserts on
(habit, date) — never clobbers a manually recorded weight.
"""

import datetime
import re
from dataclasses import dataclass

from ...models import HabitTracked

WEIGHT_SLUG = "weight"

# Matches the ``weight=<float>kg`` token the Android client writes (whitespace
# before ``kg`` is tolerated). The number is captured for parsing.
_WEIGHT_RE = re.compile(r"weight=([0-9]+(?:\.[0-9]+)?)\s*kg")


@dataclass
class WeightRecord:
    value_kg: float
    recorded_at: datetime.datetime


def parse_weight_kg(note):
    """Extract the kilogram value from a habit note, or None if absent."""
    if not note:
        return None
    match = _WEIGHT_RE.search(note)
    if match is None:
        return None
    return float(match.group(1))


def latest_weight():
    """Return the most recently recorded weight, or None if none exists.

    Walks weight events newest-first and returns the first whose note carries
    a parseable ``weight=<float>kg`` token. Global (not user-scoped), matching
    the rest of the habit-tracking endpoints.
    """
    events = HabitTracked.objects.filter(
        habit__slug=WEIGHT_SLUG, occured=True
    ).order_by("-published")

    for event in events:
        value = parse_weight_kg(event.note)
        if value is not None:
            return WeightRecord(value_kg=value, recorded_at=event.published)

    return None
