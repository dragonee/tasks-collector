"""The text columns of plans and reflections go: the lines are all there is.

Reversed, the columns come back saying what the lines say.
"""

from collections import defaultdict

from django.db import migrations


def fill_from_lines(apps, schema_editor):
    """Reverse only, once the columns are back: each says its lines."""
    Plan = apps.get_model("tree", "Plan")
    PlanLine = apps.get_model("tree", "PlanLine")
    Reflection = apps.get_model("tree", "Reflection")
    ReflectionLine = apps.get_model("tree", "ReflectionLine")

    of_plan = defaultdict(list)
    for line in PlanLine.objects.select_related("task").order_by("position", "pk"):
        of_plan[line.plan_id].append(line.task.text if line.task_id else line.text)
    for plan_id, contents in of_plan.items():
        Plan.objects.filter(pk=plan_id).update(focus_copy="\n".join(contents))

    of_reflection = defaultdict(lambda: defaultdict(list))
    for line in ReflectionLine.objects.order_by("position", "pk"):
        of_reflection[line.reflection_id][line.field].append(line.text)
    for reflection_id, fields in of_reflection.items():
        Reflection.objects.filter(pk=reflection_id).update(
            **{
                f"{field}_copy": "\n".join(contents)
                for field, contents in fields.items()
            }
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0102_text_columns_as_copies"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, fill_from_lines),
        migrations.RemoveField(model_name="plan", name="focus_copy"),
        migrations.RemoveField(model_name="reflection", name="good_copy"),
        migrations.RemoveField(model_name="reflection", name="better_copy"),
        migrations.RemoveField(model_name="reflection", name="best_copy"),
    ]
