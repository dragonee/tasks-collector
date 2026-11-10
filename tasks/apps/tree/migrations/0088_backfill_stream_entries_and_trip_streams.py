"""Every event becomes a member of its home stream, and every trip gets a
stream whose members are the events its StoryEvent rows linked."""

from django.db import migrations

# Idempotent, so it can be repeated (see the ensure_stream_entries command) to
# pick up events old code saved while this release was being deployed.
HOME_ENTRIES_SQL = """
    INSERT INTO tree_eventstreamentry (stream_id, event_id, added)
    SELECT e.event_stream_id, e.id, e.published
    FROM tree_event e
    ON CONFLICT (stream_id, event_id) DO NOTHING
"""


def forwards(apps, schema_editor):
    Story = apps.get_model("tree", "Story")
    StoryEvent = apps.get_model("tree", "StoryEvent")
    EventStream = apps.get_model("tree", "EventStream")
    EventStreamAccess = apps.get_model("tree", "EventStreamAccess")
    EventStreamEntry = apps.get_model("tree", "EventStreamEntry")

    schema_editor.execute(HOME_ENTRIES_SQL)

    for story in Story.objects.filter(event_stream__isnull=True).order_by("pk"):
        stream = EventStream.objects.create(
            type="trip", created_by_id=story.user_id, created=story.started
        )
        EventStreamAccess.objects.create(
            stream=stream, user_id=story.user_id, role="owner"
        )
        story.event_stream = stream
        story.save(update_fields=["event_stream"])

    EventStreamEntry.objects.bulk_create(
        [
            EventStreamEntry(
                stream_id=stream_id, event_id=event_id, added=created_at
            )
            for stream_id, event_id, created_at in StoryEvent.objects.values_list(
                "story__event_stream_id", "event_id", "created_at"
            )
        ],
        batch_size=1000,
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0087_eventstreamentry_story_event_stream"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
