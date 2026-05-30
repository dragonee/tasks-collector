from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0068_poi_habit"),
    ]

    operations = [
        migrations.CreateModel(
            name="PhotoAdded",
            fields=[
                (
                    "journaladded_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="tree.journaladded",
                    ),
                ),
                ("original_key", models.CharField(max_length=512)),
                (
                    "thumbnail_key",
                    models.CharField(blank=True, max_length=512, null=True),
                ),
                ("content_type", models.CharField(max_length=100)),
                ("width", models.PositiveIntegerField(blank=True, null=True)),
                ("height", models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                "abstract": False,
                "base_manager_name": "objects",
            },
            bases=("tree.journaladded",),
        ),
    ]
