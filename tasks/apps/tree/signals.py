"""
Signal handlers for the tree app.

This module contains Django signal handlers that manage event stream IDs,
create event-sourcing events, and maintain data consistency across models.
"""

from collections import namedtuple

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
    coalesce,
    observation_event_types,
)
from .uuid_generators import (
    board_event_stream_id_from_thread,
    habit_event_stream_id,
    journal_added_event_stream_id,
)

Diff = namedtuple("Diff", ["old", "new"])


def get_object_or_none(model, **kwargs):
    """
    Fetch a model instance or return None if it doesn't exist.

    Args:
        model: The model class to query.
        **kwargs: Lookup parameters passed to get().

    Returns:
        The model instance if found, None otherwise.
    """
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        return None


def fields_have_changed(instance, fields, normalize_func=lambda x: x, old_instance=...):
    """
    Check if multiple field values have changed on a model instance.

    Compares the current instance's field values against the database version.
    Returns a dict mapping field names to Diff namedtuples or False.

    Args:
        instance: The model instance being checked.
        fields: An iterable of field names to check.
        normalize_func: Optional function to normalize values before comparison.
            Useful for treating None and empty strings as equivalent.
        old_instance: The previous version of the instance. If not provided,
            fetches from database. Pass None to treat as new instance.

    Returns:
        A dict mapping each field name to either:
        - False if the field hasn't changed
        - Diff(old, new) if it has changed
        For new instances, old values will be None.
    """
    if old_instance is ...:
        old_instance = get_object_or_none(type(instance), pk=instance.pk)

    result = {}
    for field in fields:
        new_value = getattr(instance, field)
        old_value = getattr(old_instance, field) if old_instance else None

        values_equal = normalize_func(old_value) == normalize_func(new_value)

        if old_instance is None or not values_equal:
            result[field] = Diff(old=old_value, new=new_value)
        else:
            result[field] = False

    return result


def field_has_changed(instance, field, normalize_func=lambda x: x, old_instance=...):
    """
    Check if a single field value has changed on a model instance.

    See fields_have_changed for more details.
    """
    return fields_have_changed(instance, [field], normalize_func, old_instance)[field]


def old_values_from_diffs(diffs):
    """
    Extract old values as a dictionary from a dictionary of field diffs.
    """
    return {field: diff.old for field, diff in diffs.items() if diff}


def normalize_for_comparison(value):
    """Normalize None and empty strings to empty string for comparison."""
    return coalesce(value, "")


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


# XXX TODO This code contains both business logic and infrastructure code
# It should be refactored to separate the business logic from the infrastructure code
@receiver(pre_save, sender=ProjectedOutcome)
def create_projected_outcome_events(sender, instance, **kwargs):
    """
    Create event-sourcing events when a ProjectedOutcome is modified.

    Detects changes to name, description, success_criteria, and resolved_by
    fields, creating appropriate Redefined or Rescheduled events to track
    the history of changes.
    """
    if instance.pk is None:
        return

    old_instance = get_object_or_none(ProjectedOutcome, pk=instance.pk)

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
        event.save()

    # Check for rescheduled
    resolved_by_changed = field_has_changed(
        instance, "resolved_by", old_instance=old_instance
    )
    if resolved_by_changed:
        event = ProjectedOutcomeRescheduled.from_projected_outcome(
            instance, resolved_by_changed.old
        )
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
