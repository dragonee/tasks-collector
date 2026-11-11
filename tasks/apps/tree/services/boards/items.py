"""The items of a board.

``Board.state`` is a tree of items. An item is an unscheduled task: something
to do that is not planned yet. Once it is planned, ``data.taskId`` names the
task made for it; until then it is None.
"""

import uuid


def walk(items):
    """Every item of the tree, parents before their children."""
    for item in items or []:
        yield item
        yield from walk(item.get("children"))


def is_checked(item):
    """Whether the item is ticked. The web board keeps this in
    ``state.checked``; an item it has never saved has only ``data.state``."""
    state = item.get("state") or {}
    if "checked" in state:
        return bool(state["checked"])
    return (item.get("data") or {}).get("state") == "done"


def normalise(items):
    """Make every item of the tree well-formed, in place, and return the tree.

    Each item gets an id no other item of the board has (the second of two
    equal ids is replaced), a ``data.taskId``, and one answer to "is it
    ticked?": ``data.state`` follows ``state.checked``.
    """
    seen = set()
    for item in walk(items):
        item_id = item.get("id")
        if not item_id or item_id in seen:
            item_id = item["id"] = str(uuid.uuid4())
        seen.add(item_id)

        if not isinstance(item.get("data"), dict):
            item["data"] = {}
        item["data"].setdefault("taskId", None)

        checked = is_checked(item)
        item["data"]["state"] = "done" if checked else "open"
        if not isinstance(item.get("state"), dict):
            item["state"] = {}
        item["state"]["checked"] = checked
    return items


def set_checked(item, checked):
    """Tick or untick the item: ``state.checked`` is what the web board
    draws, ``data.state`` what everything else reads."""
    item.setdefault("data", {})["state"] = "done" if checked else "open"
    item.setdefault("state", {})["checked"] = checked


def text_of(item):
    """The item's text: ``data.text``, or the top-level copy the web board
    edits when there is none."""
    text = (item.get("data") or {}).get("text")
    if text is None:
        text = item.get("text", "")
    return text
