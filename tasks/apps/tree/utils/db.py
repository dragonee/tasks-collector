"""
Database utilities for the tree app.

This module contains utilities for detecting field changes on model instances
and other database-related helper functions.
"""

from collections import namedtuple

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


def get_object_or_new(model, obj):
    """
    Get the database version of an object, or a new instance if not found.

    Args:
        model: The model class to query.
        obj: The object instance (may be None or unsaved).

    Returns:
        The database version of the object, or a new model instance
        if not found or obj is None.
    """
    if not obj:
        return model()

    try:
        return model.objects.get(pk=obj.pk)
    except model.DoesNotExist:
        return model()


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
    """
    Normalize field values for comparison.

    - Treats None and empty string as equivalent
    - For strings, strips whitespace and removes carriage returns
    """
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip().replace("\r", "")
    return value
