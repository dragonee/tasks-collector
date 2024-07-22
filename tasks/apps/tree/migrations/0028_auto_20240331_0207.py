# Generated by Django 3.2.16 on 2024-03-31 02:07

from django.db import migrations, models
import django.db.models.deletion
import uuid

from tasks.apps.tree.uuid_generators import board_event_stream_id_from_thread, habit_event_stream_id, journal_added_event_stream_id

def forwards_func(apps, schema_editor):
    Board = apps.get_model('tree', 'Board')
    Observation = apps.get_model('tree', 'Observation')
    Thread = apps.get_model('tree', 'Thread')
    Habit = apps.get_model('tree', 'Habit')

    BoardCommitted = apps.get_model('tree', 'BoardCommitted')
    HabitTracked = apps.get_model('tree', 'HabitTracked')
    ObservationUpdated = apps.get_model('tree', 'ObservationUpdated')
    JournalAdded = apps.get_model('tree', 'JournalAdded')

    ContentType = apps.get_model('contenttypes', 'ContentType')

    db_alias = schema_editor.connection.alias

    for thread in Thread.objects.using(db_alias).all():
        stream_id = board_event_stream_id_from_thread(thread)
        journal_stream_id = journal_added_event_stream_id(thread)

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

        JournalAdded.objects.using(db_alias).filter(
            thread=thread,
        ).update(
            event_stream_id=journal_stream_id
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
    
    for habit in Habit.objects.using(db_alias).all():
        stream_id = habit_event_stream_id(habit)

        HabitTracked.objects.using(db_alias).filter(
            habit=habit
        ).update(
            event_stream_id=stream_id
        )

class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0027_delete_editablehabitsline'),
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
