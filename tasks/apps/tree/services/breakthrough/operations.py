"""
Lifecycle operations for ProjectedOutcome: close, move and evolve.

Operations that write more than one record run in ``transaction.atomic``,
so the emitted event and the ProjectedOutcome change either both commit or
neither does. ``created_by`` is who acts; the outcome's owner when not given.
"""

from django.db import transaction

from ...models import (
    Breakthrough,
    ProjectedOutcomeClosed,
    ProjectedOutcomeEvolved,
    ProjectedOutcomeMoved,
)


@transaction.atomic
def close_projected_outcome(projected_outcome, created_by=None):
    """
    Close a ProjectedOutcome.

    Records its final state as a ProjectedOutcomeClosed event and deletes
    the outcome; from then on it lives only in its event stream.

    Returns:
        The saved ProjectedOutcomeClosed event.
    """
    closed = ProjectedOutcomeClosed.from_projected_outcome(projected_outcome)
    closed.created_by = created_by
    closed.save()

    projected_outcome.delete()

    return closed


@transaction.atomic
def move_projected_outcome_to_next_year(projected_outcome, created_by=None):
    """
    Move a ProjectedOutcome to the following year's Breakthrough of the
    same user.

    Creates that Breakthrough if it does not exist yet and records a
    ProjectedOutcomeMoved snapshot of the outcome.

    Returns:
        The Breakthrough the outcome was moved to.
    """
    old_breakthrough = projected_outcome.breakthrough
    new_breakthrough, _ = Breakthrough.objects.get_or_create(
        user_id=old_breakthrough.user_id,
        slug=str(int(old_breakthrough.slug) + 1),
    )

    moved = ProjectedOutcomeMoved.from_projected_outcome(
        projected_outcome, old_breakthrough, new_breakthrough
    )
    moved.created_by = created_by
    moved.save()

    projected_outcome.breakthrough = new_breakthrough
    projected_outcome.save()

    return new_breakthrough


def evolve_projected_outcome(projected_outcome, note, created_by=None):
    """
    Add an evolution note to a ProjectedOutcome.

    Returns:
        The saved ProjectedOutcomeEvolved event.
    """
    evolved = ProjectedOutcomeEvolved.from_projected_outcome(projected_outcome, note)
    evolved.created_by = created_by
    evolved.save()

    return evolved
