"""Recursive helpers over the Board.state JSON tree.

Each node is a dict with keys ``id``, ``children`` (list of nodes), ``text``,
and ``data`` (which holds a ``state`` string and ``meaningfulMarkers``). See
``tasks.apps.tree.board_operations.create_task_item`` for the canonical shape.
"""

from ...board_operations import create_task_item


def _node_text(node):
    # Prefer the canonical text inside data; fall back to the top-level mirror
    # used by the legacy/frontend representation.
    data = node.get("data") or {}
    text = data.get("text")
    if text is None:
        text = node.get("text", "")
    return text


def find_task_by_text(state, text):
    """Depth-first search for a node whose text matches exactly.

    Returns ``(parent_list, index, node)`` on a hit, ``None`` otherwise.
    """
    stack = [(state, 0)]
    while stack:
        parent_list, i = stack.pop()
        if i >= len(parent_list):
            continue
        node = parent_list[i]
        if _node_text(node) == text:
            return parent_list, i, node
        stack.append((parent_list, i + 1))
        children = node.get("children") or []
        if children:
            stack.append((children, 0))
    return None


def has_children(node):
    return bool(node.get("children"))


def set_state(node, new_state):
    """Set the work state ("open" / "done") *and* the top-level
    ``state.checked`` flag the Vue Board view uses to render the checkbox.
    The two fields are kept in lockstep: a "done" node is also checked, an
    "open" node is also unchecked.
    """
    data = node.setdefault("data", {})
    data["state"] = new_state
    ui_state = node.setdefault("state", {})
    ui_state["checked"] = new_state == "done"


def get_state(node):
    return (node.get("data") or {}).get("state")


def append_task_at_root(state, text):
    node = create_task_item(text)
    state.append(node)
    return node


def rename(node, new_text):
    """Set both the top-level ``text`` mirror and the canonical
    ``data.text`` to ``new_text`` in place."""
    node["text"] = new_text
    data = node.setdefault("data", {})
    data["text"] = new_text
