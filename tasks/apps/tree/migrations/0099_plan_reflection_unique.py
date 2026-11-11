from django.db import migrations, models
from django.db.models import Count


def _join(values):
    return "\n".join(value for value in values if value) or None


def _merge_duplicates(Model, fields):
    """Fold the rows of one thread and date into the oldest of them, their
    texts joined in the order the rows were made."""
    duplicated = (
        Model.objects.values("thread", "pub_date")
        .annotate(rows=Count("pk"))
        .filter(rows__gt=1)
    )
    for key in duplicated:
        keeper, *others = Model.objects.filter(
            thread=key["thread"], pub_date=key["pub_date"]
        ).order_by("pk")
        for field in fields:
            setattr(
                keeper,
                field,
                _join(getattr(row, field) for row in [keeper, *others]),
            )
        keeper.save(update_fields=fields)
        for row in others:
            row.delete()


def forwards(apps, schema_editor):
    """Two requests arriving together could each make a plan or a reflection
    for the same thread and date. None are known; merge any there are."""
    _merge_duplicates(apps.get_model("tree", "Plan"), ["focus"])
    _merge_duplicates(apps.get_model("tree", "Reflection"), ["good", "better", "best"])


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0098_board_item_shape"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="plan",
            constraint=models.UniqueConstraint(
                fields=("thread", "pub_date"), name="plan_thread_pub_date_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="reflection",
            constraint=models.UniqueConstraint(
                fields=("thread", "pub_date"),
                name="reflection_thread_pub_date_unique",
            ),
        ),
    ]
