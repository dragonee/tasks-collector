from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0003_api_tokens"),
    ]

    operations = [
        migrations.AddField(
            model_name="apitoken",
            name="read_only",
            field=models.BooleanField(default=False),
        ),
    ]
