"""
Health data helpers for the phones' Health screens.

Body weight is the ``weight`` metric of the habit that fills each user's
weight role (the built-in weight habit, provisioned with the user, unless they
gave the role to another; see services.habits.roles).
"""

import datetime
from dataclasses import dataclass

from ...models import HabitRole
from ..habits.metrics import latest
from ..habits.roles import habit_for


@dataclass
class WeightRecord:
    value_kg: float
    recorded_at: datetime.datetime


def latest_weight(user):
    """Return ``user``'s most recently recorded weight, or None if none exists."""
    habit = habit_for(user, HabitRole.Role.WEIGHT)
    entry = latest(habit, "weight") if habit is not None else None
    if entry is None:
        return None
    return WeightRecord(value_kg=entry.values["weight"], recorded_at=entry.published)
