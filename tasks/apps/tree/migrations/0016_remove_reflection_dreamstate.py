# Generated by Django 3.2.16 on 2024-02-25 19:16

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0015_remove_board_date_closed'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='reflection',
            name='dreamstate',
        ),
    ]
