import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Typed event streams with an access list. Threads get a board and a
    journal stream (nullable until 0084 fills them)."""

    dependencies = [
        ("tree", "0082_habit_keyword_statistics_user_required"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EventStream",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("board", "Board"),
                            ("journal", "Journal"),
                            ("habit", "Habit"),
                            ("observation", "Observation"),
                            ("projected_outcome", "Projected outcome"),
                            ("trip", "Trip"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="created_event_streams",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="EventStreamAccess",
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
                (
                    "role",
                    models.CharField(
                        choices=[("owner", "Owner"), ("viewer", "Viewer")],
                        max_length=16,
                    ),
                ),
                (
                    "stream",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access",
                        to="tree.eventstream",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stream_access",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Event stream access",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("stream", "user"),
                        name="eventstreamaccess_stream_user_unique",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("role", "owner")),
                        fields=("stream",),
                        name="eventstreamaccess_one_owner_per_stream",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="thread",
            name="board_stream",
            field=models.OneToOneField(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="board_thread",
                to="tree.eventstream",
            ),
        ),
        migrations.AddField(
            model_name="thread",
            name="journal_stream",
            field=models.OneToOneField(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="journal_thread",
                to="tree.eventstream",
            ),
        ),
    ]
