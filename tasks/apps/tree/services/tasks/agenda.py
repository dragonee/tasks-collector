"""What is planned: the lines of a plan as tasks to show."""

from dataclasses import dataclass
from typing import Optional

from ...models import ReflectionLine, Thread
from ..progress import (
    base_of,
    marker_value,
    parse_progress,
    render_progress,
)
from . import documents
from .operations import MARK_BY_FIELD, display_text


@dataclass(frozen=True)
class AgendaTask:
    # As shown: a counted task with the step it is on, "Do x (2/3)".
    text: str
    done: bool
    # "~" (better) / "^" (best) for a task done with that mark.
    mark: Optional[str] = None
    # None for a plain line: nothing was done with it yet as a task.
    id: Optional[str] = None
    anchor: Optional[str] = None
    total: int = 1
    done_count: int = 0


def _plain_line(text, reflection_lines):
    """A plain plan line is done the way it was before tasks had rows: when
    its text is in the same period's reflection. A counted line's steps are
    the largest count logged for it there."""
    progress = parse_progress(text)
    if progress is None:
        for line in reflection_lines:
            if line.text == text:
                return AgendaTask(
                    text=text, done=True, mark=MARK_BY_FIELD[line.field], done_count=1
                )
        return AgendaTask(text=text, done=False)

    steps = max(
        (
            marker_value(line.text) or 0
            for line in reflection_lines
            if base_of(line.text) == base_of(text)
        ),
        default=0,
    )
    return AgendaTask(
        text=render_progress(text, progress, min(steps + 1, progress.total)),
        done=steps >= progress.total,
        total=progress.total,
        done_count=steps,
    )


def tasks_of(plan, user):
    """The lines of ``plan`` as tasks, in the plan's order; blank lines are
    left out. A task is done or not whatever plan it is read from."""
    if plan is None:
        return []

    lines = [line for line in documents.rows(plan) if line.content]

    reflection = documents.reflection_for(plan.thread, plan.pub_date)
    reflection_lines = documents.rows(reflection) if reflection is not None else []

    # The mark of a task is the field the user's own line for it is under.
    marks = {}
    done_tasks = [line.task for line in lines if line.task_id and line.task.done]
    if done_tasks:
        for line in ReflectionLine.objects.filter(
            task__in=done_tasks, reflection__thread__user=user
        ).order_by("pk"):
            marks[line.task_id] = MARK_BY_FIELD[line.field]

    tasks = []
    for line in lines:
        task = line.task
        if task is None:
            tasks.append(_plain_line(line.text, reflection_lines))
            continue
        counted = parse_progress(task.text) is not None
        tasks.append(
            AgendaTask(
                text=display_text(task),
                done=task.done,
                mark=None if counted else marks.get(task.pk),
                id=str(task.pk),
                anchor=task.anchor,
                total=task.total,
                done_count=task.done_count,
            )
        )
    return tasks


def plan_tasks(user, pub_date, thread_name):
    """The tasks of ``user``'s plan on the thread called ``thread_name`` for
    ``pub_date``; none when there is no such thread or plan."""
    thread = Thread.objects.filter(user=user, name=thread_name).first()
    if thread is None:
        return []
    return tasks_of(documents.plan_for(thread, pub_date), user)
