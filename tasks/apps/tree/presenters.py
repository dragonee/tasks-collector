from django.db.models import Q

from .models import Event, Observation, ObservationAttached, ObservationDetached


class ObservationEventPresenter:
    """Helper presenter class that contains the situation field and event at the time of the event"""

    def __init__(self, event, situation_at_event):
        self.event = event
        self.situation_at_event = situation_at_event

    def __str__(self):
        return f"{self.event} - {self.situation_at_event[:50]}..."


class ComplexPresenter:
    """Presenter class that can replay Attached/Detached events and provide complex observation information"""

    def __init__(self, observation_event_stream_id):
        self.observation_event_stream_id = observation_event_stream_id
        self._attached_stream_ids = None

    def _get_attached_stream_ids(self):
        """Replay attach/detach events to get currently attached observation stream IDs"""
        if self._attached_stream_ids is not None:
            return self._attached_stream_ids

        # Get all attach/detach events for this observation in chronological order
        attach_detach_events = (
            Event.objects.instance_of(ObservationAttached, ObservationDetached)
            .filter(event_stream_id=self.observation_event_stream_id)
            .order_by("published")
        )

        # Build a set of currently attached stream IDs by replaying events
        attached_ids = set()

        for event in attach_detach_events:
            if isinstance(event, ObservationAttached):
                attached_ids.add(event.other_event_stream_id)
            elif isinstance(event, ObservationDetached):
                attached_ids.discard(event.other_event_stream_id)

        self._attached_stream_ids = attached_ids
        return self._attached_stream_ids

    def open_observations_count(self):
        """Number of open Observations currently attached"""
        attached_stream_ids = self._get_attached_stream_ids()
        if not attached_stream_ids:
            return 0

        return Observation.objects.filter(
            event_stream_id__in=attached_stream_ids
        ).count()

    def total_unique_observations_count(self):
        """Number of total unique Observations currently attached (number of unique event_stream_id's)"""
        return len(self._get_attached_stream_ids())

    def get_attached_stream_ids(self):
        """Get the set of currently attached observation stream IDs"""
        return self._get_attached_stream_ids()

    def is_attached(self, event_stream_id):
        """Check if an observation with the given event_stream_id is currently attached"""
        attached_stream_ids = self._get_attached_stream_ids()
        return event_stream_id in attached_stream_ids

    def open_observations_list(self):
        """List of open Observations currently attached"""
        attached_stream_ids = self._get_attached_stream_ids()
        if not attached_stream_ids:
            return Observation.objects.none()

        return Observation.objects.filter(
            event_stream_id__in=attached_stream_ids
        ).order_by("-pub_date")

    def all_attached_events_chronological(self):
        """All events, chronologically sorted, for all the currently attached Observations"""
        attached_stream_ids = self._get_attached_stream_ids()
        if not attached_stream_ids:
            return Event.objects.none()

        return Event.objects.filter(event_stream_id__in=attached_stream_ids).order_by(
            "published"
        )

    def all_attached_events_with_situation(self):
        """All events with their situation at the time of the event"""
        events = self.all_attached_events_chronological()
        event_presenters = []

        for event in events:
            # Get the situation at the time of this event
            try:
                situation_at_event = (
                    event.situation_at_creation()
                    if hasattr(event, "situation_at_creation")
                    else (
                        event.situation()
                        if hasattr(event, "situation")
                        else "No situation available"
                    )
                )
            except:
                situation_at_event = "No situation available"

            event_presenters.append(
                ObservationEventPresenter(event, situation_at_event)
            )

        return event_presenters

    def _get_observation_info(self, stream_id):
        """Helper to get observation info for a given stream_id"""
        from .models import ObservationClosed

        # Try to get the open observation
        try:
            obs = Observation.objects.get(event_stream_id=stream_id)
            return {
                "event_stream_id": stream_id,
                "observation": obs,
                "is_closed": False,
            }
        except Observation.DoesNotExist:
            # Must be closed - get the ObservationClosed
            obs_closed = ObservationClosed.objects.get(event_stream_id=stream_id)
            return {
                "event_stream_id": stream_id,
                "observation_closed": obs_closed,
                "is_closed": True,
            }

    def all_attached_observations_with_status(self):
        """
        Returns a list of dicts with info about all attached observations.
        Each dict contains: event_stream_id, observation (if open), observation_closed (if closed), is_closed
        """
        return list(map(self._get_observation_info, self._get_attached_stream_ids()))


def get_complex_presenter(observation):
    if not observation.event_stream_id:
        return None

    return ComplexPresenter(observation.event_stream_id)
