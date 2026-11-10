from django.db import migrations

# Every existing event was written by the user whose stream it is in: until
# now nobody could write to someone else's stream. Idempotent.
FILL_CREATED_BY_SQL = """
    UPDATE tree_event e
    SET created_by_id = s.created_by_id
    FROM tree_eventstream s
    WHERE s.id = e.event_stream_id AND e.created_by_id IS NULL
"""


def forwards(apps, schema_editor):
    schema_editor.execute(FILL_CREATED_BY_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0090_event_created_by"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
