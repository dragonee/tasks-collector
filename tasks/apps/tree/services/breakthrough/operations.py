"""
Lifecycle operations for ProjectedOutcome: close, move and evolve.

Operations that write more than one record run in ``transaction.atomic``,
so the emitted event and the ProjectedOutcome change either both commit or
neither does.
"""

from django.db import transaction

from ...models import (
    Breakthrough,
    ProjectedOutcomeClosed,
    ProjectedOutcomeEvolved,
    ProjectedOutcomeMoved,
)


@transaction.atomic
def close_projected_outcome(projected_outcome):
    """
    Close a ProjectedOutcome.

    Records its final state as a ProjectedOutcomeClosed event and deletes
    the outcome; from then on it lives only in its event stream.

    Returns:
        The saved ProjectedOutcomeClosed event.
    """
    closed = ProjectedOutcomeClosed.from_projected_outcome(projected_outcome)
    closed.save()

    projected_outcome.delete()

    return closed


@transaction.atomic
def move_projected_outcome_to_next_year(projected_outcome):
    """
    Move a ProjectedOutcome to the following year's Breakthrough.

    Creates that Breakthrough if it does not exist yet and records a
    ProjectedOutcomeMoved snapshot of the outcome.

    Returns:
        The Breakthrough the outcome was moved to.
    """
    old_breakthrough = projected_outcome.breakthrough
    new_breakthrough, _ = Breakthrough.objects.get_or_create(
        slug=str(int(old_breakthrough.slug) + 1)
    )

    ProjectedOutcomeMoved.from_projected_outcome(
        projected_outcome, old_breakthrough, new_breakthrough
    ).save()

    projected_outcome.breakthrough = new_breakthrough
    projected_outcome.save()

    return new_breakthrough


def evolve_projected_outcome(projected_outcome, note):
    """
    Add an evolution note to a ProjectedOutcome.

    Returns:
        The saved ProjectedOutcomeEvolved event.
    """
    evolved = ProjectedOutcomeEvolved.from_projected_outcome(projected_outcome, note)
    evolved.save()

    return evolved
