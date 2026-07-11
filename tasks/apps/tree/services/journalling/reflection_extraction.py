"""
Reflection extraction from journal entries.

This module contains logic for parsing journal entries and extracting
reflection items (good/better/best) to add to the appropriate Reflection.
"""

import re
from calendar import monthrange
from datetime import timedelta

REFLECTION_LINE_PREFIXES = (
    ("[x] ", "good"),
    ("[~] ", "better"),
    ("[^] ", "best"),
)

# Optional leading whitespace and an optional markdown list bullet (``-``,
# ``*`` or ``+``) before the marker, so both ``[x] foo`` and the
# markdown-checkbox style ``- [x] foo`` are accepted and strip to ``foo``.
# This mirrors the ``- [x] <text>`` format the Android tick itself records.
_LEADING_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]\s+)?")


def extract_reflection_lines(note):
    """
    Extract reflection lines from a journal note.

    Looks for lines starting with reflection prefixes:
    - [x] for "good" items
    - [~] for "better" items
    - [^] for "best" items

    A leading markdown list bullet (``- ``, ``* `` or ``+ ``) and surrounding
    whitespace are stripped first, so ``- [x] foo`` yields ``foo`` — matching
    the board task's text rather than ``- foo``.

    CRLF / CR line endings are normalized to LF before splitting (the CLI's
    ``sanitize_string`` stores ``\\r\\n``), so a stray ``\\r`` never trails the
    extracted content — otherwise ``foo\\r`` would neither dedupe nor match the
    board task ``foo``.

    A progress marker is coerced to single-number ``(K)`` form (``coerce_to_count``),
    so a client may send either ``New task (1)`` or the displayed ``New task (1/3)``
    and both store/match as ``New task (1)``.

    Args:
        note: The journal note text to parse.

    Returns:
        List of (field_name, line_content) tuples.
    """
    # Lazy: ``today`` at module scope would cycle back through journalling.
    from ..today.progress import coerce_to_count

    normalized = note.replace("\r\n", "\n").replace("\r", "\n")
    result = []
    for raw_line in normalized.split("\n"):
        line = _LEADING_LIST_MARKER_RE.sub("", raw_line, count=1)
        for prefix, field in REFLECTION_LINE_PREFIXES:
            if line.startswith(prefix):
                result.append((field, coerce_to_count(line[len(prefix) :])))
                break
    return result


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
