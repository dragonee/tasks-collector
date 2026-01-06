"""
Reflection extraction from journal entries.

This module contains logic for parsing journal entries and extracting
reflection items (good/better/best) to add to the appropriate Reflection.
"""

from calendar import monthrange
from datetime import timedelta

REFLECTION_LINE_PREFIXES = (
    ("[x] ", "good"),
    ("[~] ", "better"),
    ("[^] ", "best"),
)


def extract_reflection_lines(note):
    """
    Extract reflection lines from a journal note.

    Looks for lines starting with reflection prefixes:
    - [x] for "good" items
    - [~] for "better" items
    - [^] for "best" items

    Args:
        note: The journal note text to parse.

    Returns:
        List of (field_name, line_content) tuples.
    """
    lines = note.split("\n")

    return [
        (field, line.replace(prefix, "", 1))
        for line in lines
        for prefix, field in REFLECTION_LINE_PREFIXES
        if prefix in line[:12]
    ]


def append_lines_to_value(value, lines):
    """
    Append lines to an existing value, handling empty cases.

    Args:
        value: The existing field value (may be None or empty).
        lines: Iterable of lines to append.

    Returns:
        The combined value with lines appended.
    """
    if not value:
        return "\n".join(lines)

    if not lines:
        return value

    return (value + "\n" + "\n".join(lines)).strip()


def add_reflection_items(journal_added):
    """
    Extract reflection items from a journal entry and add them to the Reflection.

    Parses the journal comment for reflection prefixes and adds the extracted
    items to the appropriate Reflection for the journal's thread and date.

    For Weekly threads, items are added to the end-of-week reflection.
    For big-picture threads, items are added to the end-of-month reflection.

    Args:
        journal_added: A JournalAdded instance to extract reflections from.
    """
    # Import here to avoid circular imports
    from ...models import Reflection

    pub_date = journal_added.published.date()

    # This allows us to contribute to one weekly/monthly reflection
    if journal_added.thread.name == "Weekly":
        pub_date = pub_date + timedelta(days=(6 - pub_date.weekday()))

    if journal_added.thread.name == "big-picture":
        pub_date = pub_date.replace(day=monthrange(pub_date.year, pub_date.month)[1])

    reflection_lines = extract_reflection_lines(journal_added.comment)

    if not reflection_lines:
        return

    try:
        reflection = Reflection.objects.get(
            pub_date=pub_date, thread=journal_added.thread
        )
    except Reflection.DoesNotExist:
        reflection = Reflection(pub_date=pub_date, thread=journal_added.thread)

    for field_name in ("good", "better", "best"):
        items = [line for field, line in reflection_lines if field == field_name]

        new_value = append_lines_to_value(getattr(reflection, field_name), items)

        setattr(reflection, field_name, new_value)

    reflection.save()
