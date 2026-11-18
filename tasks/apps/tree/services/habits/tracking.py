"""Tracking a habit with its metrics' values, as the phones and the API do."""

from django.core.exceptions import ValidationError
from django.utils import timezone

from ...models import HabitTracked, Thread
from .metrics import clean, write


def clean_values(habit, raw):
    """``raw`` values sent for ``habit``'s metrics, by key, as stored. Raises
    ValidationError naming each key that is no metric of the habit or whose
    value doesn't fit it."""
    metrics = {metric.key: metric for metric in habit.metrics.all()}
    values, errors = {}, {}
    for key, value in (raw or {}).items():
        metric = metrics.get(key)
        if metric is None:
            errors[key] = [f"{habit.name} has no metric {key}."]
            continue
        try:
            values[key] = clean(metric, value)
        except ValidationError as error:
            errors[key] = error.messages
    if errors:
        raise ValidationError(errors)
    return values


def track(user, habit, *, note="", values=None, published=None, **fields):
    """A new entry of ``habit`` by ``user``, on their Daily thread, with
    ``values`` (as stored, by key) written into ``note`` as tokens."""
    return HabitTracked.objects.create(
        habit=habit,
        note=write(note, habit.metrics.all(), values or {}),
        published=published or timezone.now(),
        thread=Thread.objects.daily(user),
        created_by=user,
        **fields,
    )
