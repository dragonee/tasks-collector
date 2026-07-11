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


def add_reflection_items(journal_added, comment=None):
    """
    Extract reflection items from a journal entry and add them to the Reflection.

    Parses the journal comment for reflection prefixes and adds the extracted
    items to the appropriate Reflection for the journal's thread and date.

    For Weekly threads, items are added to the end-of-week reflection.
    For big-picture threads, items are added to the end-of-month reflection.

    Args:
        journal_added: A JournalAdded instance to extract reflections from.
        comment: Optional pre-processed comment text. Defaults to
            ``journal_added.comment``.
    """
    # Imports here to avoid circular imports. ``text_lines`` lives under
    # ``services/today``; importing it at module scope would run
    # ``today/__init__`` -> ``operations`` -> ``trips`` -> back into
    # ``journalling`` (a cycle), so it is imported lazily.
    from ...models import Reflection
    from ..today import text_lines

    if comment is None:
        comment = journal_added.comment

    pub_date = journal_added.published.date()

    # This allows us to contribute to one weekly/monthly reflection
    if journal_added.thread.name == "Weekly":
        pub_date = pub_date + timedelta(days=(6 - pub_date.weekday()))

    if journal_added.thread.name == "big-picture":
        pub_date = pub_date.replace(day=monthrange(pub_date.year, pub_date.month)[1])

    reflection_lines = extract_reflection_lines(comment)

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

        new_value = text_lines.add_unique_lines(getattr(reflection, field_name), items)

        setattr(reflection, field_name, new_value)

    reflection.save()
