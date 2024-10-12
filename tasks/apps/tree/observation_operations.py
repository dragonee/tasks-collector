from django.db import transaction

from .models import JournalAdded, Event 


def migrate_observation_updates_to_journal(observation, thread_id):
    with transaction.atomic():
        for update in observation.observationupdated_set.all():
            JournalAdded.objects.create(
                published=update.published,
                thread_id=thread_id,
                comment=update.comment,
            )

        for event in Event.objects.filter(event_stream_id=observation.event_stream_id):
            event.delete()

        observation.delete()