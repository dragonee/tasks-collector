"""The text columns of plans and reflections become copies nothing reads.

Until now text written into a column was noticed the next time its document
was read, and the lines made to say the same. From here on the lines are all
there is to read, so that is done once more, for every document, before the
columns are left behind.
"""

import difflib
from collections import defaultdict

from django.db import migrations, models


def as_copy(model, field):
    """``field`` of ``model`` becomes ``<field>_copy`` over the same column:
    nothing changes in the database."""
    copy = models.TextField(db_column=field, null=True, blank=True, editable=False)
    return [
        migrations.AlterField(model_name=model, name=field, field=copy),
        migrations.RenameField(
            model_name=model, old_name=field, new_name=f"{field}_copy"
        ),
    ]


def split(text):
    if not text:
        return []
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def content(line):
    return line.task.text if getattr(line, "task_id", None) else line.text


def say(lines, wanted, new_line):
    """Make ``lines`` say ``wanted``: the lines that are still there stay
    (with their tasks), the others go, and what is new is a plain line."""
    if [content(line) for line in lines] == wanted:
        return

    result = []
    matcher = difflib.SequenceMatcher(
        None, [content(line) for line in lines], wanted, autojunk=False
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.extend(lines[i1:i2])
            continue
        for line in lines[i1:i2]:
            line.delete()
        result.extend(new_line(text) for text in wanted[j1:j2])

    for position, line in enumerate(result):
        if line.pk is None or line.position != position:
            line.position = position
            line.save()


def catch_up(apps, schema_editor):
    Plan = apps.get_model("tree", "Plan")
    PlanLine = apps.get_model("tree", "PlanLine")
    Reflection = apps.get_model("tree", "Reflection")
    ReflectionLine = apps.get_model("tree", "ReflectionLine")

    of_plan = defaultdict(list)
    for line in PlanLine.objects.select_related("task").order_by("position", "pk"):
        of_plan[line.plan_id].append(line)
    for plan in Plan.objects.iterator():
        say(
            of_plan[plan.pk],
            split(plan.focus_copy),
            lambda text, plan=plan: PlanLine(plan=plan, text=text),
        )

    of_reflection = defaultdict(list)
    for line in ReflectionLine.objects.order_by("position", "pk"):
        of_reflection[line.reflection_id, line.field].append(line)
    for reflection in Reflection.objects.iterator():
        for field in ("good", "better", "best"):
            say(
                of_reflection[reflection.pk, field],
                split(getattr(reflection, f"{field}_copy")),
                lambda text, reflection=reflection, field=field: ReflectionLine(
                    reflection=reflection, field=field, text=text
                ),
            )


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0101_backfill_task_lines"),
    ]

    operations = [
        *as_copy("plan", "focus"),
        *as_copy("reflection", "good"),
        *as_copy("reflection", "better"),
        *as_copy("reflection", "best"),
        migrations.RunPython(catch_up, migrations.RunPython.noop),
    ]
