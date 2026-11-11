"""A habit tracked from a journal entry written with \\r\\n line endings (tc,
the web form) kept the \\r of its line in its note: "#food pizza\\r". The note
was cut at \\n only (``habit_extraction.match_token_to_habit``); it is now cut
at any line ending, and the notes already kept lose their \\r.

Nothing is put back on reversal: a note never ended in \\r on purpose.
"""

from django.db import migrations
from django.db.models.functions import Length, Substr


def strip_carriage_returns(apps, schema_editor):
    HabitTracked = apps.get_model("tree", "HabitTracked")
    HabitTracked.objects.filter(note__endswith="\r").update(
        note=Substr("note", 1, Length("note") - 1)
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0103_drop_text_columns"),
    ]

    operations = [
        migrations.RunPython(strip_carriage_returns, migrations.RunPython.noop),
    ]
