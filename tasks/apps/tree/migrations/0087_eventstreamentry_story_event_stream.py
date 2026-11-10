import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Events can be members of several streams; trips get a stream
    (nullable until 0088 fills it)."""

    dependencies = [
        ("tree", "0086_event_stream_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventStreamEntry",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("added", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stream_entries",
                        to="tree.event",
                    ),
                ),
                (
                    "stream",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="tree.eventstream",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Event stream entries",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("stream", "event"),
                        name="eventstreamentry_stream_event_unique",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="story",
            name="event_stream",
            field=models.OneToOneField(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="story",
                to="tree.eventstream",
            ),
        ),
    ]
