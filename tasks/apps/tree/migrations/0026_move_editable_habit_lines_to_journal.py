from django.db import migrations
from django.utils import timezone
from datetime import datetime, time

def move_editable_habit_lines_to_journal(apps, schema_editor):
    EditableHabitsLine = apps.get_model("tree", "EditableHabitsLine")
    JournalAdded = apps.get_model("tree", "JournalAdded")

    ContentType = apps.get_model('contenttypes', 'ContentType')
    ctype = ContentType.objects.get_for_model(JournalAdded)

    db_alias = schema_editor.connection.alias

    for habits_line in EditableHabitsLine.objects.all():
        published = timezone.make_aware(
            datetime.combine(
                habits_line.pub_date,
                datetime.max.time(),
            )
        )

        JournalAdded.objects.using(db_alias).create(
            comment=habits_line.line,
            published=published,
            thread=habits_line.thread,
            polymorphic_ctype=ctype,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("tree", "0025_journaladded"),
    ]

    operations = [
        migrations.RunPython(move_editable_habit_lines_to_journal, migrations.RunPython.noop),
    ]