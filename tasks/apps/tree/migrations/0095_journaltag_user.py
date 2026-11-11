import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Journal tags get an owner (nullable until 0096 fills it). Tag slugs
    stop being globally unique; 0097 makes them unique per user instead."""

    dependencies = [
        ("tree", "0094_event_created_by_set_null"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="journaltag",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="journal_tags",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="journaltag",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
    ]
