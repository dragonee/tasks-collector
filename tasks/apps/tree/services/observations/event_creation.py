"""
Event creation for Observation domain.

This module contains logic for detecting Observation changes and
creating appropriate event-sourcing events.
"""

from django.utils import timezone

from ...models import (
    Observation,
    ObservationMade,
    ObservationRecontextualized,
    ObservationReflectedUpon,
    ObservationReinterpreted,
)
from ...utils.db import fields_have_changed, get_object_or_new, normalize_for_comparison


def create_observation_change_events(current, previous=..., published=None):
    """
    Create event-sourcing events based on observation changes.

    Compares the previous and current state of an observation and creates
    appropriate events for each type of change detected.

    Args:
        current: The current (new) state of the observation.
        previous: The previous state of the observation. If not provided,
            fetches from database.
        published: Optional timestamp for the events. Defaults to now.

    Returns:
        List of unsaved event instances to be persisted.
    """
    if previous is ...:
        previous = get_object_or_new(Observation, current)

    if not published:
        published = timezone.now()

    # New observation - pk was set
    is_new = previous.pk is None and current.pk is not None

    if is_new:
        return [ObservationMade.from_observation(current, published=published)]

    # Check which content fields changed
    changes = fields_have_changed(
        current,
        ["situation", "interpretation", "approach"],
        normalize_func=normalize_for_comparison,
        old_instance=previous,
    )

    events = []

    if changes["situation"]:
        events.append(
            ObservationRecontextualized.from_observation(
                current, previous.situation, published=published
            )
        )

    if changes["interpretation"]:
        events.append(
            ObservationReinterpreted.from_observation(
                current, previous.interpretation, published=published
            )
        )

    if changes["approach"]:
        events.append(
            ObservationReflectedUpon.from_observation(
                current, previous.approach, published=published
            )
        )

    return events
