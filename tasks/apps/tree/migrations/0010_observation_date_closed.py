# Generated by Django 3.2.10 on 2021-12-26 21:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0009_auto_20200302_2229'),
    ]

    operations = [
        migrations.AddField(
            model_name='observation',
            name='date_closed',
            field=models.DateField(blank=True, help_text='Closed', null=True),
        ),
    ]
