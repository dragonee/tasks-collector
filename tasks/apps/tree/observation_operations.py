from django.db import transaction

from .models import Event, JournalAdded


def migrate_observation_updates_to_journal(observation, thread_id):
    """Turn the observation's updates into journal entries and drop the
    observation with its whole stream.

    Deleting the stream also deletes the attach/detach records other
    (complex) observations keep about this one, so they don't point at an
    observation that no longer exists.
    """
    with transaction.atomic():
        for update in observation.observationupdated_set.all():
            JournalAdded.objects.create(
                published=update.published,
                thread_id=thread_id,
                comment=update.comment,
            )

        stream = observation.event_stream

        for event in Event.objects.filter(event_stream=stream):
            event.delete()

        observation.delete()
        stream.delete()
