"""Plans and reflections as documents of lines.

A plan is an ordered list of ``PlanLine`` rows and a reflection three ordered
lists of ``ReflectionLine`` rows (good, better, best). The rows are what is
true. The text columns (``Plan.focus``, ``Reflection.good``...) hold the same
lines joined with newlines, for everything that still reads text.

Text can be written into a column without the rows knowing: by a form, the
API, the admin, a release that predates the rows. ``ensure_lines`` (called by
``plan_for`` and ``reflection_for``, which is how the rest of the code gets a
document) notices and makes the rows say what the text says.
"""

import datetime
import difflib

from django.db import transaction

from ...models import Plan, PlanLine, Reflection, ReflectionLine, Thread
from .base import collect_garbage, create_task

PLAN_FIELDS = ("focus",)
REFLECTION_FIELDS = ("good", "better", "best")

# How alike two wordings must be to be the same line reworded, not one line
# removed and another typed in its place.
REWORDED_RATIO = 0.5


def split(text):
    """The lines of a text column; none for an empty one."""
    if not text:
        return []
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def render(contents):
    return "\n".join(contents)


def fields_of(doc):
    return PLAN_FIELDS if isinstance(doc, Plan) else REFLECTION_FIELDS


def rows(doc, field=None):
    """The lines of ``doc`` in order (of one ``field`` of a reflection)."""
    if doc.pk is None:
        return []
    lines = doc.lines.select_related("task")
    if isinstance(doc, Reflection) and field is not None:
        lines = lines.filter(field=field)
    return list(lines)


def write_cache(doc):
    """Set the text columns of ``doc`` from its lines. A column that already
    says what the lines say is left as it is, line endings and all."""
    changed = []
    for field in fields_of(doc):
        contents = [row.content for row in rows(doc, field)]
        if split(getattr(doc, field)) != contents:
            setattr(doc, field, render(contents))
            changed.append(field)
    if changed:
        doc.save(update_fields=changed)


def plans_tasks(plan):
    """Whether a line typed into ``plan`` becomes a task: on the plans of the
    built-in threads, and not once their period is over (yesterday still
    counts: the day page shows it until noon)."""
    return (
        plan.thread.name in Thread.BUILTIN_NAMES
        and plan.pub_date >= datetime.date.today() - datetime.timedelta(days=1)
    )


def worth_a_task(text):
    """A separator ("---") or a blank line is not something to do."""
    return any(character.isalnum() for character in text)


def _likeness(old, new):
    if not old.strip() or not new.strip():
        return 0
    return difflib.SequenceMatcher(None, old, new).ratio()


def _pair(old, new):
    """Which of the ``old`` rows are which of the ``new`` texts, reworded:
    {index in new: row}. Rows keep their order."""
    pairs = {}
    start = 0
    for row in old:
        best, best_likeness = None, REWORDED_RATIO
        for index in range(start, len(new)):
            likeness = _likeness(row.content, new[index])
            if likeness > best_likeness or (best is None and likeness == best_likeness):
                best, best_likeness = index, likeness
        if best is not None:
            pairs[best] = row
            start = best + 1
    return pairs


class DocumentEdit:
    """Documents rewritten as text, in one go.

    ``sync`` makes the lines of a document say what its text columns say,
    keeping the rows of lines that are still there (and with them their
    tasks). ``finish`` settles what is left: a line taken out in one place
    and typed in at another, with the same text, is still the line of its
    task; other lines typed into a plan become tasks; and a task taken off
    for good is forgotten unless something remembers it.
    """

    def __init__(self):
        # Tasks taken off a plan, and (text, task, completion) of reflection
        # lines taken out.
        self._released = []
        self._unlinked = []
        # Plan lines typed in: (row, whether it is to become a task).
        self._typed = []
        self._typed_reflection_lines = []
        self._renamed = []
        self._touched = []

    def sync(self, doc, create_tasks):
        for field in fields_of(doc):
            self._sync_field(doc, field, split(getattr(doc, field)), create_tasks)

    def _sync_field(self, doc, field, wanted, create_tasks):
        current = rows(doc, field)
        if [row.content for row in current] == wanted:
            return

        makes_tasks = create_tasks and isinstance(doc, Plan) and plans_tasks(doc)
        result = []
        reworded = []

        matcher = difflib.SequenceMatcher(
            None, [row.content for row in current], wanted, autojunk=False
        )
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            old, new = current[i1:i2], wanted[j1:j2]
            if tag == "equal":
                result.extend(old)
                continue

            # A line edited in place is the same line (and task) reworded;
            # the rest were taken out, or typed in.
            kept = _pair(old, new)
            for row in old:
                if not any(row is other for other in kept.values()):
                    self._drop(row)

            for index, text in enumerate(new):
                row = kept.get(index)
                if row is not None:
                    self._reword(row, text, makes_tasks)
                    reworded.append(row)
                else:
                    row = self._new_row(doc, field, text, makes_tasks)
                result.append(row)

        for position, row in enumerate(result):
            if row.pk is None or row.position != position or row in reworded:
                row.position = position
                row.save()

        if doc not in self._touched:
            self._touched.append(doc)

    def discard(self, doc):
        """Delete ``doc``; the tasks on it are let go like those of any line
        taken off a plan."""
        if doc.pk is None:
            return
        for row in rows(doc):
            self._drop(row)
        if doc in self._touched:
            self._touched.remove(doc)
        doc.delete()

    def _drop(self, row):
        if isinstance(row, PlanLine) and row.task_id:
            self._released.append(row.task)
        elif isinstance(row, ReflectionLine) and row.task_id:
            self._unlinked.append((row.text, row.task, row.completion))
        row.delete()

    def _reword(self, row, text, makes_tasks):
        if isinstance(row, PlanLine) and row.task_id:
            # The task reads differently on every plan it is on: bring those
            # up to date with their own text first.
            for plan in Plan.objects.filter(lines__task=row.task).exclude(
                pk=row.plan_id
            ):
                ensure_lines(plan)
            row.task.text = text
            row.task.save(update_fields=["text"])
            self._renamed.append(row.task)
            return

        row.text = text
        if isinstance(row, PlanLine):
            self._typed.append((row, makes_tasks and worth_a_task(text)))

    def _new_row(self, doc, field, text, makes_tasks):
        if isinstance(doc, Plan):
            row = PlanLine(plan=doc, text=text)
            self._typed.append((row, makes_tasks and worth_a_task(text)))
        else:
            row = ReflectionLine(reflection=doc, field=field, text=text)
            self._typed_reflection_lines.append(row)
        return row

    def _take_released(self, text):
        for task in self._released:
            if task.text == text:
                self._released.remove(task)
                return task
        return None

    def finish(self):
        for row, makes_task in self._typed:
            task = self._take_released(row.text)
            if task is not None and line_of(row.plan, task) is not None:
                # Already on this plan: the typed line is another task.
                self._released.append(task)
                task = None
            if task is None:
                if not makes_task:
                    continue
                task = create_task(row.plan.thread.user, row.text)
            row.task = task
            row.text = ""
            row.save()

        for row in self._typed_reflection_lines:
            for link in self._unlinked:
                text, task, completion = link
                if text == row.text:
                    self._unlinked.remove(link)
                    row.task, row.completion = task, completion
                    row.save(update_fields=["task", "completion"])
                    break

        collect_garbage(self._released)

        recache = list(self._touched)
        for task in self._renamed:
            for plan in Plan.objects.filter(lines__task=task):
                if plan not in recache:
                    recache.append(plan)
        for doc in recache:
            write_cache(doc)


@transaction.atomic
def sync_lines(doc, create_tasks):
    """Make the lines of ``doc`` say what its text columns say.

    ``create_tasks`` is for text someone wrote as a plan: its new lines
    become tasks. Without it they stay plain lines, which become tasks when
    something is done with them.
    """
    edit = DocumentEdit()
    edit.sync(doc, create_tasks)
    edit.finish()


@transaction.atomic
def delete(doc):
    """Delete a plan or a reflection."""
    edit = DocumentEdit()
    edit.discard(doc)
    edit.finish()


def ensure_lines(doc):
    """Catch up with text written into the columns behind the rows' back."""
    sync_lines(doc, create_tasks=False)


def plan_for(thread, pub_date, create=False):
    """The plan of ``thread`` for ``pub_date`` with its lines in step, or
    None when there is none and it isn't to be made."""
    if create:
        plan, _created = Plan.objects.get_or_create(thread=thread, pub_date=pub_date)
    else:
        plan = Plan.objects.filter(thread=thread, pub_date=pub_date).first()
        if plan is None:
            return None
    ensure_lines(plan)
    return plan


def reflection_for(thread, pub_date, create=False):
    """As ``plan_for``, for the reflection."""
    if create:
        reflection, _created = Reflection.objects.get_or_create(
            thread=thread, pub_date=pub_date
        )
    else:
        reflection = Reflection.objects.filter(thread=thread, pub_date=pub_date).first()
        if reflection is None:
            return None
    ensure_lines(reflection)
    return reflection


def _next_position(doc, field=None):
    current = rows(doc, field)
    return current[-1].position + 1 if current else 0


def line_of(plan, task):
    return PlanLine.objects.filter(plan=plan, task=task).first()


def append_task(plan, task):
    """Put ``task`` at the end of ``plan``, unless it is on it."""
    line = line_of(plan, task)
    if line is None:
        line = PlanLine.objects.create(
            plan=plan, task=task, position=_next_position(plan)
        )
        write_cache(plan)
    return line


def remove_task(plan, task):
    """Take ``task`` off ``plan``. Returns whether it was on it."""
    deleted, _ = PlanLine.objects.filter(plan=plan, task=task).delete()
    if deleted:
        write_cache(plan)
    return bool(deleted)


def bind(line, task):
    """Make a plain plan line the line of ``task``."""
    line.task = task
    line.text = ""
    line.save(update_fields=["task", "text"])


def append_reflection_line(reflection, field, text, task=None, completion=None):
    line = ReflectionLine.objects.create(
        reflection=reflection,
        field=field,
        text=text,
        task=task,
        completion=completion,
        position=_next_position(reflection, field),
    )
    write_cache(reflection)
    return line


def remove_reflection_lines(lines):
    """Delete reflection ``lines`` and refresh the text of their reflections."""
    reflections = []
    for line in lines:
        if line.reflection not in reflections:
            reflections.append(line.reflection)
        line.delete()
    for reflection in reflections:
        write_cache(reflection)


def plans_of(task):
    """The plans ``task`` is on, their lines in step."""
    plans = list(Plan.objects.filter(lines__task=task))
    for plan in plans:
        ensure_lines(plan)
    return plans


def reflections_of(task):
    """The reflections with a line of ``task``, their lines in step."""
    reflections = list(Reflection.objects.filter(lines__task=task).distinct())
    for reflection in reflections:
        ensure_lines(reflection)
    return reflections
