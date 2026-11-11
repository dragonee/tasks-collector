"""Plans and reflections as documents of lines.

A plan is an ordered list of ``PlanLine`` rows and a reflection three ordered
lists of ``ReflectionLine`` rows (good, better, best). As text
(``Plan.focus``, ``Reflection.good``...) a document is its lines, one to a
line; text is written into one with ``write`` (plain) or ``DocumentEdit.apply``
(from an editor, with anchors).

The database still has the text columns the lines came from. Nothing reads
them; ``write_copy`` keeps them saying what the lines say, so that the release
before this one could be put back.
"""

import datetime
import difflib
import re

from django.db import transaction

from ...models import Plan, PlanLine, Reflection, ReflectionLine, Task, Thread
from .base import collect_garbage, create_task

PLAN_FIELDS = ("focus",)
REFLECTION_FIELDS = ("good", "better", "best")

# How alike two wordings must be to be the same line reworded, not one line
# removed and another typed in its place.
REWORDED_RATIO = 0.5


# A line that ends with " ^t" and a task's anchor is that task's line,
# whatever its wording.
ANCHOR_RE = re.compile(r"[ \t]+\^t([0-9a-f]{8})[ \t]*$")
ANCHORS_RE = re.compile(r"[ \t]+\^t[0-9a-f]{8}(?=[ \t]*\r?$)", re.MULTILINE)


def split_anchor(line):
    """(the line without its anchor, the anchor or None)."""
    match = ANCHOR_RE.search(line)
    if match is None:
        return line, None
    return line[: match.start()], match.group(1)


def anchored(text, task):
    """``text`` as the line of ``task``."""
    return f"{text} ^t{task.anchor}"


def render_anchored(doc, field):
    """The lines of ``field`` of ``doc`` as text someone edits: a line of a
    task ends with the task's anchor."""
    return render(
        anchored(row.content, row.task) if row.task_id else row.content
        for row in rows(doc, field)
    )


def strip_anchors(text):
    """``text`` with the anchor taken off every line that ends with one."""
    return ANCHORS_RE.sub("", text)


def split(text):
    """The lines of a text; none for an empty one."""
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
    lines = doc.lines.all()
    if isinstance(doc, Reflection) and field is not None:
        lines = lines.filter(field=field)
    return list(lines)


def write_copy(doc):
    """Set the text columns of ``doc`` from its lines."""
    changed = []
    for field in fields_of(doc):
        column = f"{field}_copy"
        text = render(row.content for row in rows(doc, field))
        if (getattr(doc, column) or "") != text:
            setattr(doc, column, text)
            changed.append(column)
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

    ``write`` makes the lines of a document say what a plain text says,
    keeping the rows of lines that are still there (and with them their
    tasks); which line is which is worked out from the wording. ``apply``
    reads text whose lines carry anchors, and knows.

    ``finish`` settles what is left: a plain line taken out in one place and
    typed in at another, with the same text, is still the line of its task;
    other lines typed into a plan become tasks; and a task taken off for good
    is forgotten unless something remembers it.
    """

    def __init__(self):
        # Tasks taken off a plan, and (text, task, completion) of reflection
        # lines taken out.
        self._released = []
        self._unlinked = []
        # Plan lines typed in: (row, whether it is to become a task).
        self._typed = []
        self._typed_reflection_lines = []
        # Reflection lines put in by their anchor, to be given the completion
        # of the line of that task taken out elsewhere (a line moved from
        # good to best).
        self._anchored_reflection_lines = []
        self._renamed = []
        self._touched = []

    def write(self, doc, field, text, create_tasks=True):
        """Write plain ``text`` (no anchors) as ``field`` of ``doc``.

        ``create_tasks`` is for text someone wrote as a plan: its new lines
        become tasks (see ``plans_tasks``). Without it they stay plain
        lines, which become tasks when something is done with them.
        """
        wanted = split(text)
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

    def apply(self, doc, field, text, base=None, create_tasks=True):
        """Write ``text`` as ``field`` of ``doc``: lines as an editor has
        them, a line of a task ending with the task's anchor.

        ``base`` is the text the editor started from. Only what differs from
        it is applied, so what happened to the document meanwhile stays: a
        line added from the phone since the page was loaded is not removed
        because the page didn't have it, and one taken off elsewhere is not
        put back. Without ``base`` the text replaces what is there.

        - An anchor kept: the same line. Reworded, it renames the task (in a
          plan) or is the line's new wording (in a reflection).
        - A line taken out: off the plan, or out of the reflection (the task
          stays done).
        - A line without an anchor put in: a task (in a plan, see
          ``plans_tasks``), or a line of its own.
        - An anchor put in: that task is planned here too, or the line is
          that task's. An anchor of no task the document's owner can change
          is dropped.
        """
        current = rows(doc, field)
        is_plan = isinstance(doc, Plan)
        makes_tasks = create_tasks and is_plan and plans_tasks(doc)

        def key_of(line_text, anchor):
            return ("task", anchor) if anchor else ("text", line_text)

        def key_of_row(row):
            return key_of(row.content, row.task.anchor if row.task_id else None)

        submitted = [split_anchor(line) for line in split(text)]
        if base is None:
            loaded = [
                (row.content, row.task.anchor if row.task_id else None)
                for row in current
            ]
        else:
            loaded = [split_anchor(line) for line in split(base)]

        if submitted == loaded:
            return

        loaded_keys = [key_of(*line) for line in loaded]
        loaded_wording = {anchor: line_text for line_text, anchor in loaded if anchor}

        pool = list(current)

        def take(key):
            for row in pool:
                if key_of_row(row) == key:
                    pool.remove(row)
                    return row
            return None

        result = []
        reworded = []
        placed = set()

        for line_text, anchor in submitted:
            if anchor in placed:
                # The same anchor twice: one line per task.
                anchor = None
            key = key_of(line_text, anchor)
            row = None

            if key in loaded_keys:
                loaded_keys.remove(key)
                row = take(key)
                if row is None:
                    # Taken out elsewhere since the editor loaded it.
                    continue
                was = loaded_wording.get(anchor, row.content)
            elif anchor:
                task = (
                    Task.objects.editable_by(doc.thread.user)
                    .filter(anchor=anchor)
                    .first()
                )
                if task is None:
                    anchor, key = None, key_of(line_text, None)
                else:
                    row = take(key)
                    if row is None:
                        row = self._anchored_row(doc, field, line_text, task)
                    was = row.content

            if row is None:
                row = self._new_row(doc, field, line_text, makes_tasks, rebind=False)
            elif anchor:
                placed.add(anchor)
                if line_text.strip() and line_text != was and line_text != row.content:
                    if row.pk is None:
                        row.position = len(result)
                        row.save()
                    self._reword(row, line_text, makes_tasks)
                    reworded.append(row)
            result.append(row)

        for row in pool:
            key = key_of_row(row)
            if key in loaded_keys:
                # The editor had it and no longer does.
                loaded_keys.remove(key)
                self._drop(row)
            else:
                # Put in elsewhere since the editor loaded the document.
                result.append(row)

        for position, row in enumerate(result):
            if row.pk is None or row.position != position or row in reworded:
                row.position = position
                row.save()

        if doc not in self._touched:
            self._touched.append(doc)

    def _anchored_row(self, doc, field, text, task):
        if isinstance(doc, Plan):
            return PlanLine(plan=doc, task=task)
        row = ReflectionLine(reflection=doc, field=field, text=text, task=task)
        self._anchored_reflection_lines.append(row)
        return row

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
            row.task.text = text
            row.task.save(update_fields=["text"])
            self._renamed.append(row.task)
            return

        row.text = text
        if isinstance(row, PlanLine):
            self._typed.append((row, makes_tasks and worth_a_task(text), True))

    def _new_row(self, doc, field, text, makes_tasks, rebind=True):
        """A line typed in. ``rebind`` lets it be the line of a task taken
        out elsewhere in this edit under the same text; an editor that
        carries anchors says so itself."""
        if isinstance(doc, Plan):
            row = PlanLine(plan=doc, text=text)
            self._typed.append((row, makes_tasks and worth_a_task(text), rebind))
        else:
            row = ReflectionLine(reflection=doc, field=field, text=text)
            if rebind:
                self._typed_reflection_lines.append(row)
        return row

    def _take_released(self, text):
        for task in self._released:
            if task.text == text:
                self._released.remove(task)
                return task
        return None

    def finish(self):
        for row, makes_task, rebind in self._typed:
            task = self._take_released(row.text) if rebind else None
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

        for row in self._anchored_reflection_lines:
            for link in self._unlinked:
                _text, task, completion = link
                if task == row.task:
                    self._unlinked.remove(link)
                    row.completion = completion
                    row.save(update_fields=["completion"])
                    break

        collect_garbage(self._released)

        recache = list(self._touched)
        for task in self._renamed:
            for plan in Plan.objects.filter(lines__task=task):
                if plan not in recache:
                    recache.append(plan)
        for doc in recache:
            write_copy(doc)


@transaction.atomic
def write(doc, texts, create_tasks=False):
    """Write plain text into ``doc``: ``texts`` is {field: text}, for the
    fields to be written. See ``DocumentEdit.write``."""
    edit = DocumentEdit()
    for field, text in texts.items():
        edit.write(doc, field, text, create_tasks)
    edit.finish()


@transaction.atomic
def delete(doc):
    """Delete a plan or a reflection."""
    edit = DocumentEdit()
    edit.discard(doc)
    edit.finish()


def plan_for(thread, pub_date, create=False):
    """The plan of ``thread`` for ``pub_date``, or None when there is none
    and it isn't to be made."""
    if create:
        plan, _created = Plan.objects.get_or_create(thread=thread, pub_date=pub_date)
        return plan
    return Plan.objects.filter(thread=thread, pub_date=pub_date).first()


def reflection_for(thread, pub_date, create=False):
    """As ``plan_for``, for the reflection."""
    if create:
        reflection, _created = Reflection.objects.get_or_create(
            thread=thread, pub_date=pub_date
        )
        return reflection
    return Reflection.objects.filter(thread=thread, pub_date=pub_date).first()


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
        write_copy(plan)
    return line


def remove_task(plan, task):
    """Take ``task`` off ``plan``. Returns whether it was on it."""
    deleted, _ = PlanLine.objects.filter(plan=plan, task=task).delete()
    if deleted:
        write_copy(plan)
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
    write_copy(reflection)
    return line


def remove_reflection_lines(lines):
    """Delete reflection ``lines`` and refresh the text of their reflections."""
    reflections = []
    for line in lines:
        if line.reflection not in reflections:
            reflections.append(line.reflection)
        line.delete()
    for reflection in reflections:
        write_copy(reflection)


def plans_of(task):
    """The plans ``task`` is on."""
    return list(Plan.objects.filter(lines__task=task))
