# Generated by Django 3.2.16 on 2024-03-28 20:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0020_observationupdated'),
    ]

    operations = [
        migrations.AlterField(
            model_name='update',
            name='pub_date',
            field=models.DateField(),
        ),
    ]