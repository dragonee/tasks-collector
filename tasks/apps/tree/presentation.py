from decimal import Decimal
from django.utils import timezone
from typing import List, Optional, Union
from .models import (
    Event, ProjectedOutcome, ProjectedOutcomeMade, ProjectedOutcomeRedefined,
    ProjectedOutcomeRescheduled, ProjectedOutcomeClosed
)


class ProjectedOutcomePresentation:
    """
    Builds a ProjectedOutcome representation from a collection of events.
    This allows us to present both active and complete (event-only) ProjectedOutcomes
    in a unified way without conditional template logic.
    """
    
    def __init__(self, events: List[Event], active_instance: Optional[ProjectedOutcome] = None):
        """
        Initialize with a list of events and optionally an active ProjectedOutcome instance.
        
        Args:
            events: List of events ordered by published date
            active_instance: The actual ProjectedOutcome if it still exists (Active scenario)
        """
        self.events = sorted(events, key=lambda e: e.published)
        self.active_instance = active_instance
        self._build_state()
    
    def _decorate_with_events(self, property_name, event_type):
        """Decorate the state with the events of the given type."""
        events = [e for e in self.events if isinstance(e, event_type)]
        setattr(self, property_name, events)

    def _build_state(self):
        """Build the current state by replaying events in chronological order."""
        # Filter events by type
        self._decorate_with_events('made_events', ProjectedOutcomeMade)
        self._decorate_with_events('redefined_events', ProjectedOutcomeRedefined)
        self._decorate_with_events('rescheduled_events', ProjectedOutcomeRescheduled)
        self._decorate_with_events('closed_events', ProjectedOutcomeClosed)
     
        # Start with initial state from Made event
        if not self.made_events:
            raise ValueError("ProjectedOutcome must have at least one Made event")
        
        initial_event = self.made_events[0]
        
        # Initialize state from the Made event
        self.name = initial_event.name
        self.description = initial_event.description
        self.resolved_by = initial_event.resolved_by
        self.success_criteria = initial_event.success_criteria
        self.published = initial_event.published
        self.event_stream_id = initial_event.event_stream_id
        
        # If we have an active instance, use its current values and confidence_level
        if self.active_instance:
            self.name = self.active_instance.name
            self.description = self.active_instance.description
            self.resolved_by = self.active_instance.resolved_by
            self.success_criteria = self.active_instance.success_criteria
            self.confidence_level = self.active_instance.confidence_level
        else:
            # For complete scenarios, replay events to build final state
            self._replay_events()
            # Default confidence level for event-reconstructed state
            self.confidence_level = Decimal('100.00')
    
    def _replay_events(self):
        """Replay events in chronological order to build the final state."""
        # Apply redefined events in order
        for event in self.redefined_events:
            if event.new_name is not None:
                self.name = event.new_name
            if event.new_description is not None:
                self.description = event.new_description
            if event.new_success_criteria is not None:
                self.success_criteria = event.new_success_criteria
        
        # Apply rescheduled events in order
        for event in self.rescheduled_events:
            self.resolved_by = event.new_resolved_by
        
        # XXX: SRP violation
        # If there's a closed event, use its final state
        if self.closed_events:
            final_closed = self.closed_events[-1]
            self.name = final_closed.name
            self.description = final_closed.description
            self.resolved_by = final_closed.resolved_by
            self.success_criteria = final_closed.success_criteria
    
    @property
    def is_active(self) -> bool:
        """True if this ProjectedOutcome is still active (modifiable)."""
        return self.active_instance is not None
    
    @property
    def is_complete(self) -> bool:
        """True if this ProjectedOutcome is complete (has closed events or no active instance)."""
        return not self.is_active
    
    @property
    def status(self) -> str:
        """Human-readable status: 'Active' or 'Complete'."""
        if self.is_active:
            return 'Active'
        else:
            return 'Complete'
    
    @property
    def final_event(self) -> Optional[Event]:
        """The final event in the timeline."""
        return self.events[-1] if self.events else None
    
    @property
    def timeline_events(self) -> List[Event]:
        """All events in chronological order for timeline display."""
        return self.events
    
    @property
    def breakthrough(self):
        """Get breakthrough from active instance or try to derive from events."""
        if self.active_instance and self.active_instance.breakthrough:
            return self.active_instance.breakthrough
        
        # This is a fallback - in practice you might want to store breakthrough info in events
        return None
    
    @classmethod
    def from_event_stream_id(cls, event_stream_id: str) -> 'ProjectedOutcomePresentation':
        """
        Factory method to create a presentation from an event stream ID.
        
        Args:
            event_stream_id: UUID string of the event stream
            
        Returns:
            ProjectedOutcomePresentation instance
        """
        # Get all events for this stream
        events = list(Event.objects.filter(event_stream_id=event_stream_id).order_by('published'))
        
        # Try to get active ProjectedOutcome instance
        try:
            active_instance = ProjectedOutcome.objects.get(event_stream_id=event_stream_id)
        except ProjectedOutcome.DoesNotExist:
            active_instance = None
        
        return cls(events=events, active_instance=active_instance)
    
    def __str__(self):
        """String representation for debugging."""
        return f"ProjectedOutcomePresentation(name='{self.name}', status='{self.status}', events={len(self.events)})"
    
    def __repr__(self):
        """Detailed representation for debugging."""
        return (f"ProjectedOutcomePresentation("
                f"name='{self.name}', "
                f"status='{self.status}', "
                f"is_active={self.is_active}, "
                f"events={len(self.events)})")