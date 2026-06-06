from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0070_remove_quicknote"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddConstraint(
            model_name="event",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("idempotency_key",),
                name="event_idempotency_key_unique",
            ),
        ),
    ]
