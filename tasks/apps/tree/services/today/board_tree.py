"""Finding the board item a text names.

Clients that don't know ids yet (the Android app, a line typed into a journal)
name an unscheduled task by its text.
"""

from ..boards import items
from ..progress import base_of


def _find(state, matches):
    """Depth-first search for the first item ``matches`` accepts.

    Returns ``(parent_list, index, node)`` on a hit, ``None`` otherwise.
    """
    stack = [(state, 0)]
    while stack:
        parent_list, i = stack.pop()
        if i >= len(parent_list):
            continue
        node = parent_list[i]
        if matches(node):
            return parent_list, i, node
        stack.append((parent_list, i + 1))
        children = node.get("children") or []
        if children:
            stack.append((children, 0))
    return None


def find_unscheduled_task_by_text(state, text):
    """The first item whose text is exactly ``text``."""
    return _find(state, lambda node: items.text_of(node) == text)


def find_unscheduled_task_by_base(state, base):
    """The first item whose text without its step counter (``base_of``) is
    ``base`` — so `New task (3)` on the board is found by the base
    `New task`, whatever form the counter was typed in."""
    return _find(state, lambda node: base_of(items.text_of(node)) == base)
