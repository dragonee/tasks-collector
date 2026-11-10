import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Events record who wrote them (nullable until 0091 fills it).

    Event.event_stream changes from PROTECT to RESTRICT: still no deleting a
    stream that has events, but deleting a user works again when their events
    are filed under their own threads (the user takes threads, streams and
    events with them). A user whose events sit in another user's thread is
    refused rather than silently emptying that thread. Python-level only.
    """

    dependencies = [
        ("tree", "0089_story_event_stream_required_delete_storyevent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="created_by",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="created_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="event_stream",
            field=models.ForeignKey(
                db_column="event_stream_id",
                db_index=False,
                editable=False,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="events",
                to="tree.eventstream",
            ),
        ),
    ]
