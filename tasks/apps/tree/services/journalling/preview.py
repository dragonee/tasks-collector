"""What sending a journal entry would do, without doing it.

The entry is saved and processed as a sent one is, what that changed is read
back, and the transaction is rolled back. So the answer is what the server
would do, not a guess at it: the same reflection lines, habits and tasks.
"""

from django.db import transaction
from django.db.models import Max

from .journal_processing import process_journal_entry
from .reflection_extraction import reflection_date


def _last_event_pk():
    from ...models import Event

    return Event.objects.aggregate(last=Max("pk"))["last"] or 0


def _unscheduled_tasks(user):
    """{item id: (text, checked)} of the unscheduled tasks (the items without
    a task) of the user's current board, or {}."""
    from ..boards import items
    from ..today import operations as today

    if user is None:
        return {}
    try:
        board = today._current_board(user)
    except today.NoBoardError:
        return {}
    return {
        item.get("id"): (items.text_of(item), items.is_checked(item))
        for item in items.walk(board.state)
        if not (item.get("data") or {}).get("taskId")
    }


def preview(save, *, user, skip_habits=False, story=None):
    """What saving a journal entry with ``save`` (a function that saves it
    and returns it) and processing it would do, done and undone:

    - ``comment``: the entry as it would be kept (anchors taken off);
    - ``reflection``: the reflection its lines go to (its thread and date)
      and the lines added to its good, better and best, each with the
      anchor of the task it belongs to, if any;
    - ``habits``: what its hashtags track;
    - ``tasks_completed``: the tasks it completes;
    - ``unscheduled_tasks_ticked``: the items of the current board it ticks.
    """
    from ...models import HabitTracked, TaskCompleted
    from ..tasks import documents

    with transaction.atomic():
        last = _last_event_pk()
        board_before = _unscheduled_tasks(user)

        journal = save()
        day = reflection_date(journal)
        reflection = documents.reflection_for(journal.thread, day)
        had = {row.pk for row in documents.rows(reflection)} if reflection else set()

        process_journal_entry(journal, skip_habits=skip_habits, story=story, user=user)

        reflection = documents.reflection_for(journal.thread, day)
        added = {"good": [], "better": [], "best": []}
        for row in documents.rows(reflection) if reflection else []:
            if row.pk not in had:
                added[row.field].append(
                    {
                        "text": row.text,
                        "anchor": row.task.anchor if row.task_id else None,
                    }
                )

        # Events made since the entry was saved, by its writer: those the
        # processing made.
        made = {"pk__gt": last, "created_by_id": journal.created_by_id}
        habits = [
            {
                "habit": tracked.habit.name,
                "occured": tracked.occured,
                "note": tracked.note,
            }
            for tracked in HabitTracked.objects.filter(**made)
            .select_related("habit")
            .order_by("pk")
        ]
        completed = [
            {"text": completion.text, "anchor": completion.task.anchor}
            for completion in TaskCompleted.objects.filter(**made)
            .select_related("task")
            .order_by("pk")
        ]
        ticked = [
            text
            for item_id, (text, checked) in _unscheduled_tasks(user).items()
            if checked and not board_before.get(item_id, (text, False))[1]
        ]

        result = {
            "thread": journal.thread.name,
            "published": journal.published,
            # As kept, but with \n line endings: tc sends \r\n.
            "comment": journal.comment.replace("\r\n", "\n"),
            "reflection": {"date": day, **added},
            "habits": habits,
            "tasks_completed": completed,
            "unscheduled_tasks_ticked": ticked,
        }

        transaction.set_rollback(True)

    return result
