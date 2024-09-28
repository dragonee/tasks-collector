import re

from .models import Habit

PATTERN = re.compile(r'(?<=\s)(?=[#!])', re.MULTILINE)

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
    
    for index, candidate in enumerate(candidates):
        length = find_prefix_length(candidate, string)
        
        if length > best_length:
            best_length = length
            best_index = index
    
    return best_index, best_length

def note_to_habit_tracked_tuple(item, habit_names, habits):
    occured = True if item[0] == "#" else False

    index, length = compare(item[1:], habit_names)
    if index is None or length < 3:
        raise ValueError("Match failed on {}".format(item))
    
    habit = habits[index]
    
    # Assume first line is actually important for the habit tracked note
    return (occured, habit, item.split("\n")[0])


def habits_line_to_habits_tracked(line):
    items = PATTERN.split(' ' + line)
    items = list(filter(lambda x: x.startswith("!") or x.startswith("#"), map(lambda x: x.strip(), items)))

    habits = list(Habit.objects.all())
    habit_names = list(map(lambda x: x.tagname, habits))

    return list(map(
        lambda x: note_to_habit_tracked_tuple(x, habit_names, habits),
        items
    ))
        
    
