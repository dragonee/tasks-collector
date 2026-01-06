"""
Signal handlers for the tree app.

This module contains Django signal handlers that manage event stream IDs,
create event-sourcing events, and maintain data consistency across models.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import (
    BoardCommitted,
    Event,
    Habit,
    HabitKeyword,
    HabitTracked,
    JournalAdded,
    Observation,
    Profile,
    ProjectedOutcome,
    ProjectedOutcomeClosed,
    ProjectedOutcomeMade,
    ProjectedOutcomeMoved,
    ProjectedOutcomeRedefined,
    ProjectedOutcomeRescheduled,
    observation_event_types,
)
from .services.breakthrough.event_creation import create_projected_outcome_change_events
from .utils.db import field_has_changed
from .uuid_generators import (
    board_event_stream_id_from_thread,
    habit_event_stream_id,
    journal_added_event_stream_id,
)

# Boards and tasks


@receiver(pre_save, sender=BoardCommitted)
def update_board_committed_event_stream_id(sender, instance, *args, **kwargs):
    """On BoardCommitted save, generate event_stream_id from thread."""
    instance.event_stream_id = board_event_stream_id_from_thread(instance.thread)


# Habits


@receiver(pre_save, sender=Habit)
def on_habit_name_change_update_event_stream_id(sender, instance, *args, **kwargs):
    """
    Propagate Habit event_stream_id changes to all related HabitTracked events.
    """
    changed = field_has_changed(instance, "event_stream_id")

    if not changed or not changed.old:
        return

    Event.objects.filter(event_stream_id=changed.old).update(
        event_stream_id=changed.new
    )


@receiver(pre_save, sender=HabitTracked)
def update_habit_tracked_event_stream_id(sender, instance, *args, **kwargs):
    """Set the event_stream_id for HabitTracked from its associated habit."""
    instance.event_stream_id = habit_event_stream_id(instance)


# Observation signals


@receiver(pre_save)
def copy_observation_to_update_events(sender, instance, *args, **kwargs):
    """
    Copy observation data to observation event instances before saving.

    For observation event types, copies the thread_id (if not set) and
    event_stream_id from the related observation to maintain consistency.
    """
    if not isinstance(instance, observation_event_types):
        return

    if not instance.thread_id and instance.observation:
        instance.thread_id = instance.observation.thread_id

    instance.event_stream_id = instance.observation.event_stream_id


@receiver(pre_save, sender=Observation)
def on_observation_thread_change_update_events(sender, instance, *args, **kwargs):
    """
    Propagate thread changes to all events in the observation's event stream.

    When an Observation's thread changes, updates all related events
    to reference the new thread, maintaining consistency across the stream.
    """
    changed = field_has_changed(instance, "thread_id")

    if not changed or not changed.old:
        return

    if instance.event_stream_id is None:
        return

    Event.objects.filter(event_stream_id=instance.event_stream_id).update(
        thread=instance.thread
    )


# Journals


@receiver(pre_save, sender=JournalAdded)
def update_journal_added_event_stream_id(sender, instance, *args, **kwargs):
    """Set the event_stream_id for JournalAdded based on thread and date."""
    instance.event_stream_id = journal_added_event_stream_id(instance)


# Breakthroughs and projected outcomes


@receiver(post_save, sender=ProjectedOutcome)
def create_initial_projected_outcome_made_event(sender, instance, created, **kwargs):
    """Create a ProjectedOutcomeMade event when a new ProjectedOutcome is created."""
    if created:
        event = ProjectedOutcomeMade.from_projected_outcome(instance)
        event.save()


@receiver(pre_save, sender=ProjectedOutcome)
def create_projected_outcome_events(sender, instance, **kwargs):
    """Create event-sourcing events when a ProjectedOutcome is modified."""
    for event in create_projected_outcome_change_events(instance):
        event.save()


def _update_event_stream_id_from_projected_outcome(sender, instance, **kwargs):
    """Update event_stream_id from projected_outcome if present."""
    if instance.projected_outcome:
        instance.event_stream_id = instance.projected_outcome.event_stream_id


for _model in [
    ProjectedOutcomeMade,
    ProjectedOutcomeRedefined,
    ProjectedOutcomeRescheduled,
    ProjectedOutcomeClosed,
    ProjectedOutcomeMoved,
]:
    pre_save.connect(_update_event_stream_id_from_projected_outcome, sender=_model)


# Habit keywords


@receiver(post_save, sender=Profile)
def add_all_habit_keywords_to_new_profile(sender, instance, created, **kwargs):
    """When a new Profile is created, add all existing HabitKeywords to it"""
    if created:
        all_keywords = HabitKeyword.objects.all()
        instance.habit_keywords.set(all_keywords)


@receiver(post_save, sender=HabitKeyword)
def add_new_habit_keyword_to_all_profiles(sender, instance, created, **kwargs):
    """When a new HabitKeyword is created, add it to all existing Profiles"""
    if created:
        all_profiles = Profile.objects.all()
        for profile in all_profiles:
            profile.habit_keywords.add(instance)
