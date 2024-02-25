# Generated by Django 3.2.16 on 2024-02-25 00:25

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import tasks.apps.tree.models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0012_alter_board_state'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('published', models.DateTimeField(auto_now_add=True)),
                ('thread', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tree.thread')),
            ],
        ),
        migrations.AlterField(
            model_name='board',
            name='date_started',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.CreateModel(
            name='BoardCommitted',
            fields=[
                ('event_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='tree.event')),
                ('focus', models.CharField(max_length=255)),
                ('before', models.JSONField(default=tasks.apps.tree.models.default_state)),
                ('after', models.JSONField(default=tasks.apps.tree.models.default_state)),
                ('transitions', models.JSONField(default=tasks.apps.tree.models.empty_dict)),
                ('date_started', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            bases=('tree.event',),
        ),
    ]
