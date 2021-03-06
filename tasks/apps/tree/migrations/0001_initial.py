# Generated by Django 2.1.7 on 2019-10-30 18:29

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import tasks.apps.tree.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Board',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_started', models.DateTimeField(auto_now_add=True)),
                ('date_closed', models.DateTimeField(blank=True, null=True)),
                ('state', django.contrib.postgres.fields.jsonb.JSONField(default=tasks.apps.tree.models.default_state)),
            ],
        ),
    ]
