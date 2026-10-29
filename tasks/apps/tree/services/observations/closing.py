"""
Closing open Observations.

Closing records an ObservationClosed event on the observation's stream and
removes the Observation row; the stream's other events are kept.
"""

from django.db import transaction

from ...models import Observation, ObservationClosed


def close_observation(observation_id, published=None):
    """
    Close an open observation.

    The Observation row is locked for the duration of the close, so two
    concurrent closes of the same observation (e.g. a double-clicked Close
    button) record a single ObservationClosed: the second waits for the
    first to commit and then finds the row gone.

    Args:
        observation_id: Primary key of the open observation.
        published: Optional timestamp. Defaults to now.

    Returns:
        The saved ObservationClosed event.

    Raises:
        Observation.DoesNotExist: If no open observation has this id.
    """
    with transaction.atomic():
        observation = Observation.objects.select_for_update().get(pk=observation_id)

        observation_closed = ObservationClosed.from_observation(
            observation, published=published
        )
        observation_closed.save()

        observation.delete()

    return observation_closed
