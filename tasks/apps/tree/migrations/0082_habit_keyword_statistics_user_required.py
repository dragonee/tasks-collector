import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0081_assign_habit_owners_and_provision_habits"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="habit",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="habits",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="habitkeyword",
            name="user",
            field=models.ForeignKey(
                editable=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="habit_keywords",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="statistics",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="statistics",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="habit",
            constraint=models.UniqueConstraint(
                fields=("user", "slug"), name="habit_user_slug_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="habitkeyword",
            constraint=models.UniqueConstraint(
                fields=("user", "keyword"), name="habitkeyword_user_keyword_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="statistics",
            constraint=models.UniqueConstraint(
                fields=("user", "key"), name="statistics_user_key_unique"
            ),
        ),
    ]
