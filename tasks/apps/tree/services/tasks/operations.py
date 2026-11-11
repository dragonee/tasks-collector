"""What can be done with a task: plan it, complete it, take it back.

Every operation is one transaction. Rows are locked in one order: the board
a task is linked to, then the task, then plans and reflections.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from ...models import JournalAdded, ReflectionLine, Task, TaskCompleted, Thread
from ..boards import items
from ..idempotency import existing_event
from ..progress import base_of, marker_value, parse_progress, render_count
from ..progress import render_progress as _render_progress
from . import board_links, documents
from .base import board_thread_of, collect_garbage, create_task

# The mark a completion carries, as journal lines write it ("[~] text"), and
# the reflection field it lands in.
FIELD_BY_MARK = {
    None: ReflectionLine.Field.GOOD,
    "~": ReflectionLine.Field.BETTER,
    "^": ReflectionLine.Field.BEST,
}
MARK_BY_FIELD = {
    ReflectionLine.Field.GOOD: None,
    ReflectionLine.Field.BETTER: "~",
    ReflectionLine.Field.BEST: "^",
}


def step_text(task, step):
    """How a reflection records that ``step`` of the task is done: the
    task's text, its counter (if it has one) showing the step: "Do x (2)"."""
    progress = parse_progress(task.text)
    if progress is None:
        return task.text
    return render_count(task.text, progress, step)


def display_text(task):
    """The task's text as lists show it: a counted task with the step it is
    on, "Do x (2/3)"; anything else as written."""
    progress = parse_progress(task.text)
    if progress is None:
        return task.text
    return _render_progress(
        task.text, progress, min(task.done_count + 1, progress.total)
    )


def same_task_text(task_text, text):
    """Whether ``text`` names the task: its text exactly or, for a counted
    task, with the counter in any form ("Do x (3)", "Do x (2/3)")."""
    if task_text == text:
        return True
    if parse_progress(task_text) is None or parse_progress(text) is None:
        return False
    return base_of(task_text) == base_of(text)


def task_for_item(user, board, item):
    """The task of a board item, made now when the item is an unscheduled
    task, or when its task is done (the item is being planned anew). The
    board must be row-locked; it is saved here when a task is made."""
    task_id = (item.get("data") or {}).get("taskId")
    if task_id:
        task = Task.objects.filter(pk=task_id).first()
        if task is not None and not task.done:
            return task

    task = create_task(user, items.text_of(item))
    board_links.link(task, board, item)
    board.save()
    return task


def adopt(task, reflection):
    """Take over what a plain plan line had going for it before it became
    ``task``: the lines of ``reflection`` (of the line's own plan period) that
    recorded it done are the task's, and the task is as done as they say."""
    if reflection is None:
        return

    counted = parse_progress(task.text) is not None
    steps = 0
    for line in documents.rows(reflection):
        if line.task_id is not None:
            continue
        if counted:
            if base_of(line.text) != base_of(task.text):
                continue
            value = marker_value(line.text)
            if value is None:
                continue
            steps = max(steps, value)
        elif line.text == task.text:
            steps = 1
        else:
            continue
        line.task = task
        line.save(update_fields=["task"])

    if steps:
        task.done_count = steps
        if task.done:
            task.completed_at = timezone.now()
        task.save(update_fields=["done_count", "completed_at"])


@transaction.atomic
def plan(task, plan):
    """Put ``task`` on ``plan`` (once)."""
    return documents.append_task(plan, task)


@transaction.atomic
def unplan(task, plan):
    """Take ``task`` off ``plan``. The task stays if anything remembers it."""
    documents.remove_task(plan, task)
    collect_garbage([task])


@transaction.atomic
def move(task, from_plan, to_plan):
    documents.append_task(to_plan, task)
    documents.remove_task(from_plan, task)


@transaction.atomic
def rename(task, text):
    """Give ``task`` another text. It reads so on every plan it is on, and
    so does its board item."""
    board = board_links.locked_board_of(task)
    task = Task.objects.select_for_update().get(pk=task.pk)

    task.text = text
    task.save(update_fields=["text"])
    for plan in documents.plans_of(task):
        documents.write_copy(plan)

    if board is not None:
        board_links.set_text(board, task)

    return task


def _planners(task):
    """The users who have ``task`` on one of their plans."""
    return get_user_model().objects.filter(threads__plan__lines__task=task).distinct()


def _journal(actor, marker_text, note, published, story):
    """The journal entry of a completion that came with a note, or that was
    saved to a trip: "- [x] <text>" and the note below it, on the actor's
    Daily thread.

    It is not run through ``process_journal_entry``: the "[x]" would be read
    as a reflection line and complete the task a second time.
    """
    marker = f"- [x] {marker_text}"
    journal = JournalAdded.objects.create(
        thread=Thread.objects.daily(actor),
        comment=f"{marker}\n{note}" if note else marker,
        published=published,
        created_by=actor,
    )
    if story is not None:
        story.add(journal)
    return journal


@transaction.atomic
def complete(
    task,
    actor,
    *,
    day,
    at=None,
    mark=None,
    note=None,
    story=None,
    idempotency_key=None,
    reflection=None,
    wording=None,
):
    """Record that ``actor`` did a step of ``task`` on ``day``: the whole
    task, or the next of its counted steps.

    - A ``TaskCompleted`` event, once per ``idempotency_key``.
    - A reflection line for the actor and for everyone else who has the task
      on a plan: in their Daily reflection of ``day`` (the actor's goes into
      ``reflection`` when one is given, worded as ``wording`` if they put
      it their own way), under good, or better / best for the mark ``~`` /
      ``^``.
    - The task's board item is ticked once the task is done.
    - ``note`` or ``story`` (a trip) make a journal entry of the actor's.

    Returns the event; for a task without steps that is already done, the
    one that did it (None when that predates events).
    """
    existing = existing_event(TaskCompleted, actor, idempotency_key)
    if existing is not None:
        return existing

    board = board_links.locked_board_of(task)
    task = Task.objects.select_for_update().get(pk=task.pk)

    if task.done and parse_progress(task.text) is None:
        # A task without steps is done once; only a counted one goes on
        # ("add another").
        return task.completions.order_by("-published", "-pk").first()

    at = at or timezone.now()
    step = task.done_count + 1
    text = step_text(task, step)

    completion = TaskCompleted.objects.create(
        task=task,
        thread=board_thread_of(task),
        published=at,
        day=day,
        text=text,
        created_by=actor,
        idempotency_key=idempotency_key or None,
    )

    task.done_count = step
    if task.done and task.completed_at is None:
        task.completed_at = at
    task.save(update_fields=["done_count", "completed_at"])

    field = FIELD_BY_MARK[mark]
    others = [user for user in _planners(task) if user != actor]
    for user in [actor, *others]:
        if user == actor and reflection is not None:
            target = reflection
        else:
            target = documents.reflection_for(
                Thread.objects.daily(user), day, create=True
            )
        documents.append_reflection_line(
            target,
            field,
            wording if user == actor and wording else text,
            task=task,
            completion=completion,
        )

    if task.done and board is not None:
        board_links.set_ticked(board, task, True)

    if note or story is not None:
        completion.journal = _journal(actor, display_text(task), note, at, story)
        completion.save(update_fields=["journal"])

    return completion


@transaction.atomic
def reopen(task):
    """Take back the last step done on ``task``: its event and the
    reflection lines written with it go, and its board item is unticked when
    the task is open again. Journal entries stay.

    Returns False when no step was done.
    """
    board = board_links.locked_board_of(task)
    task = Task.objects.select_for_update().get(pk=task.pk)

    if task.done_count == 0:
        return False

    completion = task.completions.order_by("-published", "-pk").first()
    if completion is not None:
        lines = list(completion.reflection_lines.select_related("reflection"))
    else:
        # Done before completions were events (see ``adopt``).
        lines = list(
            task.reflection_lines.filter(
                completion__isnull=True, text=step_text(task, task.done_count)
            ).select_related("reflection")
        )
    documents.remove_reflection_lines(lines)
    if completion is not None:
        completion.delete()

    task.done_count -= 1
    if not task.done:
        task.completed_at = None
    task.save(update_fields=["done_count", "completed_at"])

    if board is not None and not task.done:
        board_links.set_ticked(board, task, False)

    return True
