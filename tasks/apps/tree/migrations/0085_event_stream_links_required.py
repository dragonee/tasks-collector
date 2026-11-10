import django.db.models.deletion
from django.db import migrations, models


def stream_link(related_name):
    """The event_stream_id UUID column, now a link to its EventStream row.

    The column keeps its name, so altering it only adds the foreign key and
    unique constraints; the rename that follows is a no-op in the database.
    """
    return models.OneToOneField(
        db_column="event_stream_id",
        editable=False,
        on_delete=django.db.models.deletion.RESTRICT,
        related_name=related_name,
        to="tree.eventstream",
    )


class Migration(migrations.Migration):
    """Threads always have their streams, and observations, habits and
    projected outcomes link to theirs (0084 created a row for every id)."""

    dependencies = [
        ("tree", "0084_backfill_event_streams"),
    ]

    operations = [
        migrations.AlterField(
            model_name="thread",
            name="board_stream",
            field=models.OneToOneField(
                editable=False,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="board_thread",
                to="tree.eventstream",
            ),
        ),
        migrations.AlterField(
            model_name="thread",
            name="journal_stream",
            field=models.OneToOneField(
                editable=False,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="journal_thread",
                to="tree.eventstream",
            ),
        ),
    ] + [
        operation
        for model_name, related_name in (
            ("observation", "observation"),
            ("habit", "habit"),
            ("projectedoutcome", "projected_outcome"),
        )
        for operation in (
            migrations.AlterField(
                model_name=model_name,
                name="event_stream_id",
                field=stream_link(related_name),
            ),
            migrations.RenameField(
                model_name=model_name,
                old_name="event_stream_id",
                new_name="event_stream",
            ),
        )
    ]
