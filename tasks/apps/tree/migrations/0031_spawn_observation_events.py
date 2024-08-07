# Generated by Django 3.2.16 on 2024-03-28 20:31

from django.db import migrations

from tasks.apps.tree.utils.datetime import aware_from_date


def forwards_func(apps, schema_editor):
    ObservationMade = apps.get_model("tree", "ObservationMade")
    ObservationClosed = apps.get_model("tree", "ObservationClosed")
    Observation = apps.get_model("tree", "Observation")

    ContentType = apps.get_model('contenttypes', 'ContentType')

    db_alias = schema_editor.connection.alias

    observationmade_ct = ContentType.objects.get_for_model(ObservationMade)
    observationclosed_ct = ContentType.objects.get_for_model(ObservationClosed)

    for observation in Observation.objects.using(db_alias):
        ObservationMade.objects.create(
            published=aware_from_date(observation.pub_date),
            event_stream_id=observation.event_stream_id,
            thread_id=observation.thread_id,
            type_id=observation.type_id,
            situation=observation.situation,
            interpretation=observation.interpretation,
            approach=observation.approach,
            polymorphic_ctype=observationmade_ct,
        )

        if not observation.date_closed:
            continue

        ObservationClosed.objects.using(db_alias).create(
            published=aware_from_date(observation.date_closed),
            event_stream_id=observation.event_stream_id,
            thread_id=observation.thread_id,
            type_id=observation.type_id,
            situation=observation.situation,
            interpretation=observation.interpretation,
            approach=observation.approach,
            polymorphic_ctype=observationclosed_ct,
        )

        observation.delete()

def reverse_func(apps, schema_editor):
    ObservationMade = apps.get_model("tree", "ObservationMade")
    ObservationClosed = apps.get_model("tree", "ObservationClosed")
    Observation = apps.get_model("tree", "Observation")

    db_alias = schema_editor.connection.alias

    for observation_closed in ObservationClosed.objects.using(db_alias).all():
        observation_made = ObservationMade.objects.using(db_alias).get(
            event_stream_id=observation_closed.event_stream_id
        )

        Observation.objects.using(db_alias).create(
            event_stream_id=observation_closed.event_stream_id,
            thread_id=observation_closed.thread_id,
            type_id=observation_closed.type_id,
            situation=observation_closed.situation,
            interpretation=observation_closed.interpretation,
            approach=observation_closed.approach,
            date_closed=observation_closed.published.date(),
            pub_date=observation_made.published.date(),
        )

    ObservationMade.objects.using(db_alias).all().delete()
    ObservationClosed.objects.using(db_alias).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0030_observationclosed_observationmade_observationrecontextualized_observationreflectedupon_observationre'),
    ]

    operations = [
         migrations.RunPython(forwards_func, reverse_func),
    ]
