"""What is planned: the lines of a plan as tasks to show."""

from dataclasses import dataclass
from typing import Optional

from ...models import PlanLine, ReflectionLine, Task, Thread
from ...utils.datetime import make_last_day_of_the_month, make_last_day_of_the_week
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
    # The Task itself; None for a plain line.
    task: Optional[Task] = None


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


def _marks(tasks, user):
    """{task id: mark} for those of ``tasks`` that are done: the mark of a
    task is the field the user's own line for it is under."""
    done = [task for task in tasks if task.done]
    if not done:
        return {}
    lines = ReflectionLine.objects.filter(
        task__in=done, reflection__thread__user=user
    ).order_by("pk")
    return {line.task_id: MARK_BY_FIELD[line.field] for line in lines}


def of_task(task, marks):
    """``task`` as a task to show; ``marks`` as ``_marks`` gives them."""
    counted = parse_progress(task.text) is not None
    return AgendaTask(
        text=display_text(task),
        done=task.done,
        mark=None if counted else marks.get(task.pk),
        id=str(task.pk),
        anchor=task.anchor,
        total=task.total,
        done_count=task.done_count,
        task=task,
    )


def task_shown(task, user):
    """One task as a task to show to ``user``."""
    return of_task(task, _marks([task], user))


def tasks_of(plan, user):
    """The lines of ``plan`` as tasks, in the plan's order; blank lines are
    left out. A task is done or not whatever plan it is read from."""
    if plan is None:
        return []

    lines = [line for line in documents.rows(plan) if line.content]

    reflection = documents.reflection_for(plan.thread, plan.pub_date)
    reflection_lines = documents.rows(reflection) if reflection is not None else []

    marks = _marks([line.task for line in lines if line.task_id], user)

    return [
        (
            _plain_line(line.text, reflection_lines)
            if line.task is None
            else of_task(line.task, marks)
        )
        for line in lines
    ]


def period_end(thread_name, day):
    """The date of the plan of the thread called ``thread_name`` that ``day``
    falls in: the day for Daily, the Sunday for Weekly, the last day of the
    month for big-picture."""
    if thread_name == Thread.WEEKLY:
        return make_last_day_of_the_week(day)
    if thread_name == Thread.BIG_PICTURE:
        return make_last_day_of_the_month(day)
    return day


def describe(shown, user):
    """What clients are told about each of ``shown`` (``AgendaTask``s): a
    list of dicts. Which of the user's plans a task is on and which board its
    item is on are looked up for all of them at once."""
    tasks = [one.task for one in shown if one.task is not None]

    plans = {}
    lines = (
        PlanLine.objects.filter(task__in=tasks, plan__thread__user=user)
        .select_related("plan__thread")
        .order_by("plan__pub_date")
    )
    for line in lines:
        plans.setdefault(line.task_id, []).append(
            {"thread": line.plan.thread.name, "pub_date": line.plan.pub_date}
        )

    boards = {
        task.pk: task.board
        for task in Task.objects.filter(
            pk__in=[task.pk for task in tasks if task.board_id]
        ).select_related("board__thread")
    }

    described = []
    for one in shown:
        task = one.task
        board = boards.get(task.pk) if task is not None else None
        described.append(
            {
                # None for a plain line: nothing was done with it as a task.
                "id": one.id,
                "anchor": one.anchor,
                # As written, and as lists show it: a counted task with the
                # step it is on.
                "text": task.text if task is not None else one.text,
                "display": one.text,
                "done": one.done,
                "mark": one.mark,
                "total": one.total,
                "done_count": one.done_count,
                "completed_at": task.completed_at if task is not None else None,
                "board": (
                    {
                        "id": board.pk,
                        "item_id": task.board_item_id,
                        "thread": board.thread.name,
                    }
                    if board is not None
                    else None
                ),
                "plans": plans.get(task.pk, []) if task is not None else [],
            }
        )
    return described


def plan_tasks(user, pub_date, thread_name):
    """The tasks of ``user``'s plan on the thread called ``thread_name`` for
    ``pub_date``; none when there is no such thread or plan."""
    thread = Thread.objects.filter(user=user, name=thread_name).first()
    if thread is None:
        return []
    return tasks_of(documents.plan_for(thread, pub_date), user)
