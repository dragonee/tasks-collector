"""
Habit tracking parsing utilities.

This module provides functions for parsing habit tokens from text
and matching them to Habit instances.
"""

import re

from .models import Habit

PATTERN = re.compile(r"(?<=\s)(?=[#!])", re.MULTILINE)


# Pure parsing functions (no DB queries)


def find_prefix_length(a, b):
    """Find the length of the common prefix between two strings."""
    j = -1
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            break
        j = i
    return j + 1


def find_best_keyword_match(string, keywords):
    """
    Find the best matching keyword for a string based on prefix matching.

    Args:
        string: The string to match against keywords.
        keywords: Iterable of keyword strings to match.

    Returns:
        Tuple of (index, length, keyword) for the best match,
        or (None, 0, None) if no match found.
    """
    best_index = None
    best_length = 0
    best_keyword = None

    for index, candidate in enumerate(keywords):
        length = find_prefix_length(candidate, string)

        if length > best_length:
            best_length = length
            best_index = index
            best_keyword = candidate

    return best_index, best_length, best_keyword


def parse_habit_tokens(line):
    """
    Parse a line into habit tokens (# or ! prefixed items).

    Args:
        line: Text line containing habit markers.

    Returns:
        List of stripped tokens starting with # or !.
    """
    items = PATTERN.split(" " + line)
    return [x.strip() for x in items if x.strip().startswith(("!", "#"))]


def match_token_to_habit(token, habits_from_keywords):
    """
    Match a single token to a habit.

    Args:
        token: String starting with # (occurred) or ! (skipped).
        habits_from_keywords: Dict mapping keywords to Habit instances.

    Returns:
        Tuple of (occurred, habit, note) or None if no match.

    Raises:
        ValueError: If token doesn't match any keyword with >= 3 char prefix.
    """
    occurred = token[0] == "#"

    index, length, keyword = find_best_keyword_match(
        token[1:], habits_from_keywords.keys()
    )

    if index is None or length < 3:
        raise ValueError(f"Match failed on {token}")

    habit = habits_from_keywords[keyword]
    note = token.split("\n")[0]

    return (occurred, habit, note)


def match_token_to_habit_or_none(token, habits_from_keywords):
    """Match a token to a habit, returning None on failure."""
    try:
        return match_token_to_habit(token, habits_from_keywords)
    except ValueError:
        return None


def match_tokens_to_habits(tokens, habits_from_keywords):
    """
    Match a list of tokens to habits.

    Args:
        tokens: List of habit tokens (# or ! prefixed).
        habits_from_keywords: Dict mapping keywords to Habit instances.

    Returns:
        List of (occurred, habit, note) tuples for matched tokens.
    """
    return [
        m
        for m in (match_token_to_habit_or_none(t, habits_from_keywords) for t in tokens)
        if m is not None
    ]


def build_keyword_to_habit_map(habits):
    """
    Build a mapping from keywords to habits.

    Args:
        habits: Iterable of Habit instances.

    Returns:
        Dict mapping each keyword to its Habit.
    """
    return {keyword: habit for habit in habits for keyword in habit.get_keywords()}


# Orchestration function (with DB query)


def habits_line_to_habits_tracked(line, habits=None):
    """
    Parse a line and return matched habit tracking tuples.

    Args:
        line: Text line containing habit markers (# or !).
        habits: Optional iterable of Habit instances. If not provided,
            fetches all habits from the database.

    Returns:
        List of (occurred, habit, note) tuples for each matched habit.
    """
    tokens = parse_habit_tokens(line)

    if not tokens:
        return []

    if habits is None:
        habits = Habit.objects.all()

    habits_from_keywords = build_keyword_to_habit_map(habits)

    return match_tokens_to_habits(tokens, habits_from_keywords)
