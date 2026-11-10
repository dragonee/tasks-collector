"""
Signal handlers for the tree app.

Provisioning of new users, protection of built-in threads, creation of
projected-outcome events, and data consistency across models. Which stream
an event belongs to is decided by the event itself (``Event.save``).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import (
    Event,
    HabitKeyword,
    Observation,
    Profile,
    ProjectedOutcome,
    ProjectedOutcomeMade,
    Thread,
)
from .services.breakthrough.event_creation import create_projected_outcome_change_events
from .services.provisioning import provision_user
from .utils.db import field_has_changed

# Users and threads


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def provision_new_user(sender, instance, created, raw=False, **kwargs):
    """Every new user gets the built-in threads, their boards and a profile.

    Skipped for ``loaddata`` (``raw``): fixtures carry their own rows.
    """
    if created and not raw:
        provision_user(instance)


@receiver(pre_delete, sender=Thread)
def protect_builtin_threads(sender, instance, origin=None, **kwargs):
    """Built-in threads can't be deleted, except along with their owner."""
    if not instance.is_builtin:
        return

    origin_model = getattr(origin, "model", None) or getattr(
        getattr(origin, "_meta", None), "model", None
    )
    if origin_model is get_user_model():
        return

    raise ProtectedError(
        f"The built-in thread {instance.name!r} can't be deleted.", {instance}
    )


# Observations


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


# Habit keywords


@receiver(post_save, sender=Profile)
def add_users_habit_keywords_to_new_profile(sender, instance, created, **kwargs):
    """A new Profile starts with all of its user's habit keywords selected."""
    if created:
        instance.habit_keywords.set(HabitKeyword.objects.filter(user=instance.user_id))


@receiver(post_save, sender=HabitKeyword)
def add_new_habit_keyword_to_owners_profile(sender, instance, created, **kwargs):
    """A new habit keyword is selected in its owner's Profile."""
    if created:
        for profile in Profile.objects.filter(user=instance.user_id):
            profile.habit_keywords.add(instance)
