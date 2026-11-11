from django.db.models import Q

from .models import (
    Event,
    EventStream,
    Observation,
    ObservationAttached,
    ObservationClosed,
    ObservationDetached,
    OtherObservationMixin,
)


class ObservationEventPresenter:
    """Helper presenter class that contains the situation field and event at the time of the event"""

    def __init__(self, event, situation_at_event):
        self.event = event
        self.situation_at_event = situation_at_event

    def __str__(self):
        return f"{self.event} - {self.situation_at_event[:50]}..."


class ComplexPresenter:
    """Presenter class that can replay Attached/Detached events and provide complex observation information

    Whoever can read the complex observation sees everything attached to it:
    sharing a complex observation shares its attached observations.
    """

    def __init__(self, observation_event_stream_id, user=None):
        self.observation_event_stream_id = observation_event_stream_id
        # Who reads the attached events: see load_other_observations.
        self.user = user
        self._replayed_stream_ids = None

    def _replay_attached_stream_ids(self):
        """Replay attach/detach events to get currently attached observation stream IDs"""
        if self._replayed_stream_ids is not None:
            return self._replayed_stream_ids

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

        self._replayed_stream_ids = attached_ids
        return self._replayed_stream_ids

    def open_observations_count(self):
        """Number of open Observations currently attached"""
        attached_stream_ids = self._replay_attached_stream_ids()
        if not attached_stream_ids:
            return 0

        return Observation.objects.filter(
            event_stream_id__in=attached_stream_ids
        ).count()

    def total_unique_observations_count(self):
        """Number of total unique Observations currently attached (number of unique event_stream_id's)"""
        return len(self._replay_attached_stream_ids())

    def get_attached_stream_ids(self):
        """Get the set of currently attached observation stream IDs"""
        return self._replay_attached_stream_ids()

    def is_attached(self, event_stream_id):
        """Check if an observation with the given event_stream_id is currently attached"""
        return event_stream_id in self._replay_attached_stream_ids()

    def open_observations_list(self):
        """List of open Observations currently attached"""
        attached_stream_ids = self._replay_attached_stream_ids()
        if not attached_stream_ids:
            return Observation.objects.none()

        return Observation.objects.filter(
            event_stream_id__in=attached_stream_ids
        ).order_by("-pub_date")

    def all_attached_events_chronological(self):
        """All events, chronologically sorted, for all the currently attached Observations"""
        attached_stream_ids = self._replay_attached_stream_ids()
        if not attached_stream_ids:
            return Event.objects.none()

        return load_other_observations(
            Event.objects.filter(event_stream_id__in=attached_stream_ids).order_by(
                "published"
            ),
            self.user,
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

    def all_attached_observations_with_status(self):
        """
        Returns a list of dicts with info about all attached observations.
        Each dict contains: event_stream_id, observation (if open), observation_closed (if closed), is_closed
        """
        stream_ids = self._replay_attached_stream_ids()
        observations = observations_by_stream(stream_ids)

        def info(stream_id):
            observation = observations[stream_id]
            if isinstance(observation, ObservationClosed):
                return {
                    "event_stream_id": stream_id,
                    "observation_closed": observation,
                    "is_closed": True,
                }
            return {
                "event_stream_id": stream_id,
                "observation": observation,
                "is_closed": False,
            }

        return [
            info(stream_id) for stream_id in stream_ids if stream_id in observations
        ]


def observations_by_stream(stream_ids):
    """The observation of each of ``stream_ids`` that has one, by stream id:
    the Observation while it is open, its latest ObservationClosed once it is
    closed. Two queries."""
    found = {
        observation.event_stream_id: observation
        for observation in Observation.objects.filter(event_stream_id__in=stream_ids)
    }
    closed = ObservationClosed.objects.filter(
        event_stream_id__in=set(stream_ids) - found.keys()
    ).order_by("published")
    for observation in closed:
        found[observation.event_stream_id] = observation
    return found


def load_other_observations(events, user):
    """``events`` as a list, each attach and detach event among them with the
    observation on its other end (``other_observation``) and whether ``user``
    may open it (``other_observation_visible``), which
    ``events/_other_observation.html`` shows: three queries for all of them.
    """
    events = list(events)
    linked = [event for event in events if isinstance(event, OtherObservationMixin)]
    if not linked:
        return events

    stream_ids = {event.other_event_stream_id for event in linked}
    observations = observations_by_stream(stream_ids)
    visible = set()
    if user is not None and user.is_authenticated:
        visible = set(
            EventStream.objects.visible_to(user)
            .filter(pk__in=stream_ids)
            .values_list("pk", flat=True)
        )

    for event in linked:
        event.other_observation = observations.get(event.other_event_stream_id)
        event.other_observation_visible = event.other_event_stream_id in visible
    return events


def get_complex_presenter(observation, user):
    if not observation.event_stream_id:
        return None

    return ComplexPresenter(observation.event_stream_id, user)
