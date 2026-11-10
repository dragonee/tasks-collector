import django.db.models.deletion
from django.db import migrations, models


def check_every_stream_id_has_a_row(apps, schema_editor):
    """0084 created a stream row for every id in use, and since then every
    stream is created as a row first. Anything else is a bug to look at, not
    something to paper over here."""
    Event = apps.get_model("tree", "Event")
    EventStream = apps.get_model("tree", "EventStream")
    streams = EventStream.objects.values("pk")

    orphans = {
        "event_stream_id": Event.objects.exclude(event_stream_id__in=streams),
        "other_event_stream_id (attached)": apps.get_model(
            "tree", "ObservationAttached"
        ).objects.exclude(other_event_stream_id__in=streams),
        "other_event_stream_id (detached)": apps.get_model(
            "tree", "ObservationDetached"
        ).objects.exclude(other_event_stream_id__in=streams),
    }
    counts = {name: rows.count() for name, rows in orphans.items()}
    if any(counts.values()):
        raise RuntimeError(
            f"Events refer to streams that have no row: {counts}. "
            "Find out how they were created, then migrate."
        )


class Migration(migrations.Migration):
    """Events link to their stream row, and attach/detach records to the
    stream of the other observation.

    The columns keep their names, so altering them only adds foreign key
    constraints; the renames that follow are no-ops in the database. The
    (event_stream_id, published) index stays as it is.
    """

    dependencies = [
        ("tree", "0085_event_stream_links_required"),
    ]

    operations = [
        migrations.RunPython(
            check_every_stream_id_has_a_row, reverse_code=migrations.RunPython.noop
        ),
        migrations.AlterField(
            model_name="event",
            name="event_stream_id",
            field=models.ForeignKey(
                db_column="event_stream_id",
                db_index=False,
                editable=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="events",
                to="tree.eventstream",
            ),
        ),
        migrations.RenameField(
            model_name="event",
            old_name="event_stream_id",
            new_name="event_stream",
        ),
    ] + [
        operation
        for model_name, verb in (
            ("observationattached", "attached"),
            ("observationdetached", "detached"),
        )
        for operation in (
            migrations.AlterField(
                model_name=model_name,
                name="other_event_stream_id",
                field=models.ForeignKey(
                    db_column="other_event_stream_id",
                    editable=False,
                    help_text=f"Event stream of the observation being {verb}",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="+",
                    to="tree.eventstream",
                ),
            ),
            migrations.RenameField(
                model_name=model_name,
                old_name="other_event_stream_id",
                new_name="other_event_stream",
            ),
        )
    ]
