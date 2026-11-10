"""One EventStream row for every stream id in use, and a board and journal
stream for every thread.

Ids are kept: an existing stream's row has the id its events already carry,
so URLs and API filters by event_stream_id keep working. Every stream gets
its owner as created_by and as its single access entry.
"""

import uuid
from collections import defaultdict

from django.db import migrations
from django.db.models import Min
from django.utils import timezone

from tasks.apps.tree.migrations._legacy_stream_ids import (
    BOARD_URL,
    JOURNAL_URL,
    thread_event_stream_id,
)

BOARD = "board"
JOURNAL = "journal"
HABIT = "habit"
OBSERVATION = "observation"
PROJECTED_OUTCOME = "projected_outcome"

# The kind of stream each event model's events belong to.
EVENT_STREAM_TYPES = {
    "boardcommitted": BOARD,
    "journaladded": JOURNAL,
    "photoadded": JOURNAL,
    "habittracked": HABIT,
    "observationmade": OBSERVATION,
    "observationupdated": OBSERVATION,
    "observationrecontextualized": OBSERVATION,
    "observationreinterpreted": OBSERVATION,
    "observationreflectedupon": OBSERVATION,
    "observationclosed": OBSERVATION,
    "insightrefined": OBSERVATION,
    "observationattached": OBSERVATION,
    "observationdetached": OBSERVATION,
    "projectedoutcomemade": PROJECTED_OUTCOME,
    "projectedoutcomeredefined": PROJECTED_OUTCOME,
    "projectedoutcomerescheduled": PROJECTED_OUTCOME,
    "projectedoutcomeclosed": PROJECTED_OUTCOME,
    "projectedoutcomemoved": PROJECTED_OUTCOME,
    "projectedoutcomeevolved": PROJECTED_OUTCOME,
}


class Streams:
    """Collects the type, owner and start time of every stream id."""

    def __init__(self):
        self.types = defaultdict(set)
        self.owners = {}
        self.started = {}

    def add(self, stream_id, type_, owner_id, started=None):
        self.types[stream_id].add(type_)
        # Sources are added most authoritative first.
        if owner_id is not None:
            self.owners.setdefault(stream_id, owner_id)
        if started is not None and (
            stream_id not in self.started or started < self.started[stream_id]
        ):
            self.started[stream_id] = started


THREAD_STREAMS = (
    ("board_stream_id", BOARD_URL, BOARD, ("boardcommitted",)),
    ("journal_stream_id", JOURNAL_URL, JOURNAL, ("journaladded", "photoadded")),
)


def _thread_streams(apps, streams):
    """Each thread's board and journal stream id.

    Their ids were derived from the thread name alone, so every user's
    "Daily" shared one. The oldest thread with a name keeps the id; any
    other gets a new one.

    A thread's board commits and journal entries then belong to its streams,
    as Event.save derives them from now on: the ones of a thread that got a
    new id move to it, and so do a few old ones that carry another thread's
    id.
    """
    Thread = apps.get_model("tree", "Thread")
    Event = apps.get_model("tree", "Event")

    taken = set()
    threads = list(Thread.objects.order_by("pk"))
    for thread in threads:
        for field, url, type_, event_models in THREAD_STREAMS:
            stream_id = thread_event_stream_id(url, thread)
            if stream_id in taken:
                stream_id = uuid.uuid4()
            taken.add(stream_id)
            setattr(thread, field, stream_id)
            streams.add(stream_id, type_, thread.user_id)

            Event.objects.filter(
                thread_id=thread.pk, polymorphic_ctype__model__in=event_models
            ).exclude(event_stream_id=stream_id).update(event_stream_id=stream_id)
    return threads


def _check_unique(model, field):
    distinct = model.objects.values(field).order_by().distinct().count()
    if distinct != model.objects.count():
        raise RuntimeError(
            f"Several {model.__name__} rows share an event_stream_id; each must "
            "have a stream of its own. Fix them, then migrate."
        )


def forwards(apps, schema_editor):
    Event = apps.get_model("tree", "Event")
    Observation = apps.get_model("tree", "Observation")
    Habit = apps.get_model("tree", "Habit")
    ProjectedOutcome = apps.get_model("tree", "ProjectedOutcome")
    ObservationAttached = apps.get_model("tree", "ObservationAttached")
    ObservationDetached = apps.get_model("tree", "ObservationDetached")
    Thread = apps.get_model("tree", "Thread")
    EventStream = apps.get_model("tree", "EventStream")
    EventStreamAccess = apps.get_model("tree", "EventStreamAccess")

    for model in (Observation, Habit, ProjectedOutcome):
        _check_unique(model, "event_stream_id")

    streams = Streams()

    # What a stream is about knows its owner best, so it goes first.
    threads = _thread_streams(apps, streams)
    for stream_id, user_id in Observation.objects.values_list(
        "event_stream_id", "user_id"
    ):
        streams.add(stream_id, OBSERVATION, user_id)
    for stream_id, user_id in Habit.objects.values_list("event_stream_id", "user_id"):
        streams.add(stream_id, HABIT, user_id)
    for stream_id, user_id in ProjectedOutcome.objects.values_list(
        "event_stream_id", "breakthrough__user_id"
    ):
        streams.add(stream_id, PROJECTED_OUTCOME, user_id)

    # Every stream that has events; closed observations and outcomes exist
    # only here. Their owner is whoever owns the threads they are filed under.
    unknown = {}
    for row in (
        Event.objects.values("event_stream_id", "polymorphic_ctype__model")
        .annotate(owner=Min("thread__user_id"), started=Min("published"))
        .order_by()
    ):
        model = row["polymorphic_ctype__model"]
        if model not in EVENT_STREAM_TYPES:
            unknown[model] = unknown.get(model, 0) + 1
            continue
        streams.add(
            row["event_stream_id"],
            EVENT_STREAM_TYPES[model],
            row["owner"],
            row["started"],
        )
    if unknown:
        raise RuntimeError(
            "Events of unknown kinds (model: streams) can't be given a stream "
            f"type: {unknown}. Remove or convert them, then migrate."
        )

    # Observations another one was attached to, possibly deleted since.
    for model in (ObservationAttached, ObservationDetached):
        for row in (
            model.objects.values("other_event_stream_id")
            .annotate(owner=Min("thread__user_id"))
            .order_by()
        ):
            streams.add(row["other_event_stream_id"], OBSERVATION, row["owner"])

    mixed = {str(k): sorted(v) for k, v in streams.types.items() if len(v) > 1}
    if mixed:
        raise RuntimeError(
            f"Streams mixing kinds of events can't be typed: {mixed}. "
            "Fix them, then migrate."
        )
    ownerless = [str(k) for k in streams.types if k not in streams.owners]
    if ownerless:
        raise RuntimeError(f"Streams without an owner: {ownerless}.")

    now = timezone.now()
    EventStream.objects.bulk_create(
        [
            EventStream(
                id=stream_id,
                type=next(iter(types)),
                created_by_id=streams.owners[stream_id],
                created=streams.started.get(stream_id, now),
            )
            for stream_id, types in streams.types.items()
        ],
        batch_size=1000,
    )
    EventStreamAccess.objects.bulk_create(
        [
            EventStreamAccess(stream_id=stream_id, user_id=owner_id, role="owner")
            for stream_id, owner_id in streams.owners.items()
        ],
        batch_size=1000,
    )
    Thread.objects.bulk_update(
        threads, ["board_stream_id", "journal_stream_id"], batch_size=1000
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0083_eventstream"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
