import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0078_assign_thread_owners_and_provision_users"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="thread",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="threads",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="breakthrough",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="breakthroughs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="thread",
            constraint=models.UniqueConstraint(
                fields=("user", "name"), name="thread_user_name_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="breakthrough",
            constraint=models.UniqueConstraint(
                fields=("user", "slug"), name="breakthrough_user_slug_unique"
            ),
        ),
    ]
