import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Every trip has its stream; StoryEvent is replaced by the trip stream's
    entries (0088 copied them)."""

    dependencies = [
        ("tree", "0088_backfill_stream_entries_and_trip_streams"),
    ]

    operations = [
        migrations.AlterField(
            model_name="story",
            name="event_stream",
            field=models.OneToOneField(
                editable=False,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="story",
                to="tree.eventstream",
            ),
        ),
        migrations.DeleteModel(
            name="StoryEvent",
        ),
    ]
