"""
String utilities for the tree app.
"""


def coalesce(value, default=""):
    """Return value if not None, otherwise return default."""
    return value if value is not None else default
