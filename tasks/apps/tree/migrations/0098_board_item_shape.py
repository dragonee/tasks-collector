import uuid

from django.db import migrations


def _walk(items):
    for item in items or []:
        yield item
        yield from _walk(item.get("children"))


def _is_checked(item):
    state = item.get("state") or {}
    if "checked" in state:
        return bool(state["checked"])
    return (item.get("data") or {}).get("state") == "done"


def _normalise(items):
    """A copy of ``services.boards.items.normalise`` as it was when this
    migration was written."""
    seen = set()
    for item in _walk(items):
        item_id = item.get("id")
        if not item_id or item_id in seen:
            item_id = item["id"] = str(uuid.uuid4())
        seen.add(item_id)

        if not isinstance(item.get("data"), dict):
            item["data"] = {}
        item["data"].setdefault("taskId", None)

        checked = _is_checked(item)
        item["data"]["state"] = "done" if checked else "open"
        if not isinstance(item.get("state"), dict):
            item["state"] = {}
        item["state"]["checked"] = checked
    return items


def forwards(apps, schema_editor):
    """Give every board item an id of its own, an empty task link and one
    answer to "is it ticked?".

    Most items had no id (the web board made up a new one on every load), and
    an item ticked on the web kept ``data.state`` "open".
    """
    Board = apps.get_model("tree", "Board")

    for board in Board.objects.all():
        if not isinstance(board.state, list):
            continue
        _normalise(board.state)
        board.save(update_fields=["state"])


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0097_journaltag_user_required"),
    ]

    operations = [
        # Nothing to undo: the old code reads the new shape.
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
