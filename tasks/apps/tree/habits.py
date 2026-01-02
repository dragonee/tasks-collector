import re

from .models import Habit

PATTERN = re.compile(r"(?<=\s)(?=[#!])", re.MULTILINE)


def find_prefix_length(a, b):
    j = -1
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            break
        j = i
    return j + 1


def compare(string, candidates):
    best_index = None
    best_length = 0
    best_keyword = None

    for index, candidate in enumerate(candidates):
        length = find_prefix_length(candidate, string)

        if length > best_length:
            best_length = length
            best_index = index
            best_keyword = candidate

    return best_index, best_length, best_keyword


def note_to_habit_tracked_tuple(item, habits_from_keywords: dict[str, Habit]):
    occured = True if item[0] == "#" else False

    index, length, keyword = compare(item[1:], habits_from_keywords.keys())
    if index is None or length < 3:
        raise ValueError("Match failed on {}".format(item))

    habit = habits_from_keywords[keyword]

    # Assume first line is actually important for the habit tracked note
    return (occured, habit, item.split("\n")[0])


def note_to_habit_tracked_tuple_or_none(item, habits_from_keywords):
    try:
        return note_to_habit_tracked_tuple(item, habits_from_keywords)
    except ValueError:
        return None


def habits_line_to_habits_tracked(line):
    items = PATTERN.split(" " + line)
    items = list(
        filter(
            lambda x: x.startswith("!") or x.startswith("#"),
            map(lambda x: x.strip(), items),
        )
    )

    if len(items) == 0:
        return []

    habits = Habit.objects.all()

    habits_from_keywords = {}
    for habit in habits:
        for keyword in habit.get_keywords():
            habits_from_keywords[keyword] = habit

    return list(
        filter(
            None,
            map(
                lambda x: note_to_habit_tracked_tuple_or_none(x, habits_from_keywords),
                items,
            ),
        )
    )
