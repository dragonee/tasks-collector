import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """created_by is required, and an idempotency key is unique per writer
    instead of globally."""

    dependencies = [
        ("tree", "0091_backfill_event_created_by"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="created_by",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="created_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="event",
            name="event_idempotency_key_unique",
        ),
        migrations.AddConstraint(
            model_name="event",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("created_by", "idempotency_key"),
                name="event_created_by_idempotency_key_unique",
            ),
        ),
    ]
