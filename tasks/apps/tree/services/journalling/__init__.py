"""
Journalling domain services.

This module provides services for processing journal entries, including
reflection extraction and habit tracking.

Exported functions:

    process_journal_entry(journal_added, skip_habits=False)
        Main orchestration function for journal entry processing.
        Use this when saving a new journal entry to:
        - Extract reflection items ([x], [~], [^]) and add them to Reflections
        - Parse habit markers (#habit, !habit) and create HabitTracked entries

        Used by: JournalAddedViewSet, journal_add view

    habits_line_to_habits_tracked(line, habits=None)
        Parse a text line and return matched habit tracking tuples.
        Use this for form validation when you need to parse habit markers
        without creating database entries.

        Used by: SingleHabitTrackedForm for validating habit input
"""

from .habit_extraction import habits_line_to_habits_tracked
from .journal_processing import process_journal_entry

__all__ = [
    "habits_line_to_habits_tracked",
    "process_journal_entry",
]
