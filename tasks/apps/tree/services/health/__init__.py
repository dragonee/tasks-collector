"""
Health data helpers for the phones' Health screens.

Body weight is the ``weight`` metric of each user's ``weight`` Habit
(provisioned with the user, see services.provisioning). It is a separate Habit
from the daily ``health-metrics`` one so the hourly background sync, which
replaces the day's entry, never clobbers a weight recorded by hand.
"""

import datetime
from dataclasses import dataclass

from ...models import Habit
from ..habits.metrics import latest

WEIGHT_SLUG = "weight"


@dataclass
class WeightRecord:
    value_kg: float
    recorded_at: datetime.datetime


def latest_weight(user):
    """Return ``user``'s most recently recorded weight, or None if none exists."""
    habit = Habit.objects.filter(user=user, slug=WEIGHT_SLUG).first()
    entry = latest(habit, "weight") if habit is not None else None
    if entry is None:
        return None
    return WeightRecord(value_kg=entry.values["weight"], recorded_at=entry.published)
