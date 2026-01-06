"""
Event creation for ProjectedOutcome (breakthrough) domain.

This module contains logic for detecting ProjectedOutcome changes and
creating appropriate event-sourcing events.
"""

from ...models import (
    ProjectedOutcome,
    ProjectedOutcomeRedefined,
    ProjectedOutcomeRescheduled,
)
from ...utils.db import (
    field_has_changed,
    fields_have_changed,
    get_object_or_none,
    normalize_for_comparison,
    old_values_from_diffs,
)


def create_projected_outcome_change_events(instance):
    """
    Create event-sourcing events when a ProjectedOutcome is modified.

    Detects changes to name, description, success_criteria, and resolved_by
    fields, creating appropriate Redefined or Rescheduled events to track
    the history of changes.

    Args:
        instance: The ProjectedOutcome instance being saved.

    Returns:
        List of unsaved event instances to be persisted.
    """
    if instance.pk is None:
        return []

    old_instance = get_object_or_none(ProjectedOutcome, pk=instance.pk)

    events = []

    # Check for redefined fields (name, description, success_criteria)
    redefined_changes = fields_have_changed(
        instance,
        ["name", "description", "success_criteria"],
        normalize_func=normalize_for_comparison,
        old_instance=old_instance,
    )

    redefined_fields = old_values_from_diffs(redefined_changes)

    if redefined_fields:
        event = ProjectedOutcomeRedefined.from_projected_outcome(
            instance, redefined_fields
        )
        events.append(event)

    # Check for rescheduled
    resolved_by_changed = field_has_changed(
        instance, "resolved_by", old_instance=old_instance
    )
    if resolved_by_changed:
        event = ProjectedOutcomeRescheduled.from_projected_outcome(
            instance, resolved_by_changed.old
        )
        events.append(event)

    return events
