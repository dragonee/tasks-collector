# Generated by Django 3.2.16 on 2024-03-31 02:07

from django.db import migrations, models
import django.db.models.deletion
import uuid

from tasks.apps.tree.uuid_generators import board_event_stream_id_from_thread

def forwards_func(apps, schema_editor):
    Board = apps.get_model('tree', 'Board')
    Observation = apps.get_model('tree', 'Observation')
    Thread = apps.get_model('tree', 'Thread')


    BoardCommitted = apps.get_model('tree', 'BoardCommitted')
    HabitTracked = apps.get_model('tree', 'HabitTracked')
    ObservationUpdated = apps.get_model('tree', 'ObservationUpdated')

    ContentType = apps.get_model('contenttypes', 'ContentType')

    db_alias = schema_editor.connection.alias

    for thread in Thread.objects.using(db_alias).all():
        stream_id = board_event_stream_id_from_thread(thread)

        Board.objects.using(db_alias).filter(
            thread=thread,
        ).update(
            event_stream_id=stream_id
        )

        BoardCommitted.objects.using(db_alias).filter(
            thread=thread,
        ).update(
            event_stream_id=stream_id
        )

    for observation in Observation.objects.using(db_alias).all():
        stream_id = uuid.uuid4()

        observation.event_stream_id = stream_id
        observation.save()

        ObservationUpdated.objects.using(db_alias).filter(
            observation=observation    
        ).update(
            event_stream_id=stream_id
        )
    
    for tracked in HabitTracked.objects.using(db_alias).all():
        tracked.event_stream_id = uuid.uuid4()
        tracked.save()


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0024_auto_20240328_2122'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='event',
            options={'ordering': ('published',)},
        ),
        migrations.AddField(
            model_name='board',
            name='event_stream_id',
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='event_stream_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AddField(
            model_name='observation',
            name='event_stream_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AlterField(
            model_name='observationupdated',
            name='observation',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='tree.observation'),
        ),
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['published'], name='tree_event_publish_59896f_idx'),
        ),
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['event_stream_id', 'published'], name='tree_event_event_s_f2ebb8_idx'),
        ),
        migrations.RunPython(forwards_func, migrations.RunPython.noop),
    ]
