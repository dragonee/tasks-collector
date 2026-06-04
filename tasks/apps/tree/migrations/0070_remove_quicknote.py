from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0069_photoadded"),
    ]

    operations = [
        migrations.DeleteModel(
            name="QuickNote",
        ),
    ]
