import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Deleting a user who wrote in someone else's stream (an editor's commits
    on a shared board) keeps those events, with no writer, instead of refusing
    the deletion."""

    dependencies = [
        ("tree", "0093_shared_boards"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="created_by",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
