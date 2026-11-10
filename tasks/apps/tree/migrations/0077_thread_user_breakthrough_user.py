import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Threads and breakthroughs get an owner (nullable until 0078 fills it).

    The breakthrough year (slug) stops being globally unique; 0079 makes it
    unique per user instead.
    """

    dependencies = [
        ("tree", "0076_alter_boardcommitted_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="thread",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="threads",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="breakthrough",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="breakthroughs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="breakthrough",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
    ]
