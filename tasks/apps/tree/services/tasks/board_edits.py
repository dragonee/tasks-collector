"""What someone did on a board to the items that have tasks.

The web board saves its whole tree. For an item with a task, the tree does
not say what happened (it may predate what the phone did); the browser says
it in so many words, as operations sent along with the tree.
"""

from django.utils import timezone

from ...models import Task
from . import operations as tasks


def apply(board, actor, ops):
    """Carry out ``ops`` on the tasks of ``board``'s items, as ``actor``.

    Each op is a dict: ``{"op": "complete", "item_id", "day", "at"?, "key"?}``,
    ``{"op": "reopen", "item_id"}`` or ``{"op": "rename", "item_id", "text"}``.
    Ticking an item with a step counter does one step of its task. An op
    about an item of this board that has no task is skipped: the tree it
    came from knew a task this board no longer has.
    """
    for op in ops:
        task = Task.objects.filter(board=board, board_item_id=op["item_id"]).first()
        if task is None:
            continue

        if op["op"] == "complete":
            tasks.complete(
                task,
                actor,
                day=op["day"],
                at=op.get("at") or timezone.now(),
                idempotency_key=op.get("key"),
            )
        elif op["op"] == "reopen":
            tasks.reopen(task)
        elif op["op"] == "rename":
            tasks.rename(task, op["text"])
