"""Every board has a thread: boards are found through their thread's user,
so one without would be invisible to everyone. None is without one on
production (the copy of 2026-11-11); a board without a thread stops this
migration rather than being guessed an owner."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0104_habit_notes_without_carriage_returns"),
    ]

    operations = [
        migrations.AlterField(
            model_name="board",
            name="thread",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="tree.thread"
            ),
        ),
    ]
