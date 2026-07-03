from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0074_weight_habit"),
    ]

    operations = [
        migrations.AddField(
            model_name="photoadded",
            name="content_hash",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
    ]
