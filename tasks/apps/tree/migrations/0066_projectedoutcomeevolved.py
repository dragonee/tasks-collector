from django.db import migrations, models
import django.db.models.deletion
import tasks.apps.tree.models


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0065_insightrefined"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectedOutcomeEvolved",
            fields=[
                (
                    "event_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="tree.event",
                    ),
                ),
                ("note", models.CharField(max_length=512)),
                (
                    "projected_outcome",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="tree.projectedoutcome",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "base_manager_name": "objects",
            },
            bases=("tree.event", tasks.apps.tree.models.ProjectedOutcomeEventMixin),
        ),
    ]
