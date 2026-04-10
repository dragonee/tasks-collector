"""
Insight extraction and refinement for closed Observation streams.

This module contains logic for creating InsightRefined events
from closed observations.
"""

from django.core.exceptions import ValidationError
from django.utils import timezone

from ...models import InsightRefined, ObservationClosed


def extract_insight(event_stream_id, *, situation=None, approach=None, published=None):
    """
    Create the next InsightRefined for a stream that has been closed.

    Uses the latest InsightRefined as the base if one exists,
    otherwise falls back to the ObservationClosed event.

    Args:
        event_stream_id: The event stream UUID.
        situation: Optional override for the situation text.
        approach: Optional override for the approach text.
        published: Optional timestamp. Defaults to now.

    Returns:
        An unsaved InsightRefined instance.

    Raises:
        ValidationError: If no ObservationClosed exists for the stream.
    """
    observation_closed = (
        ObservationClosed.objects.filter(event_stream_id=event_stream_id)
        .order_by("-published")
        .first()
    )

    if observation_closed is None:
        raise ValidationError("Cannot extract insight: observation is not closed.")

    latest_insight = (
        InsightRefined.objects.filter(event_stream_id=event_stream_id)
        .order_by("-published")
        .first()
    )

    base = latest_insight or observation_closed

    return InsightRefined.from_observation_closed(
        observation_closed,
        situation=situation if situation is not None else base.situation,
        approach=approach if approach is not None else base.approach,
        published=published,
    )
