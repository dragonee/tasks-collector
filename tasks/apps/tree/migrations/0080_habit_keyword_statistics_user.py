import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Habits, habit keywords and statistics get an owner (nullable until
    0081 fills it). Habit slugs, keywords and statistic keys stop being
    globally unique; 0082 makes them unique per user instead."""

    dependencies = [
        ("tree", "0079_thread_user_breakthrough_user_required"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="habit",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="habits",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="habitkeyword",
            name="user",
            field=models.ForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="habit_keywords",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="statistics",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="statistics",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="habit",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
        migrations.AlterField(
            model_name="habitkeyword",
            name="keyword",
            field=models.SlugField(allow_unicode=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="statistics",
            name="key",
            field=models.CharField(max_length=255),
        ),
    ]
