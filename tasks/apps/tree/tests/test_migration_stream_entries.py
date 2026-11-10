"""0087-0089: every event becomes a member of its home stream; every trip
gets a stream whose members are what its StoryEvent rows linked."""

import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

BEFORE = [("tree", "0087_eventstreamentry_story_event_stream")]
AFTER = [("tree", "0089_story_event_stream_required_delete_storyevent")]


class StreamEntryBackfillTestCase(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        self.old_apps = executor.loader.project_state(BEFORE).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(AFTER)
        return executor.loader.project_state(AFTER).apps

    def _model(self, name):
        return self.old_apps.get_model("tree", name)

    def _stream(self, user, type_):
        stream = self._model("EventStream").objects.create(type=type_, created_by=user)
        self._model("EventStreamAccess").objects.create(
            stream=stream, user=user, role="owner"
        )
        return stream

    def test_events_join_their_home_stream_and_trips_get_streams(self):
        user = self.old_apps.get_model("common", "User").objects.create(
            username="dragonee"
        )
        daily = self._model("Thread").objects.create(
            user=user,
            name="Daily",
            board_stream=self._stream(user, "board"),
            journal_stream=self._stream(user, "journal"),
        )
        ContentType = self.old_apps.get_model("contenttypes", "ContentType")
        note = self._model("JournalAdded").objects.create(
            thread=daily,
            event_stream=daily.journal_stream,
            comment="on the way",
            published=timezone.now(),
            polymorphic_ctype=ContentType.objects.get_or_create(
                app_label="tree", model="journaladded"
            )[0],
        )
        started = timezone.make_aware(datetime.datetime(2026, 7, 1, 9))
        story = self._model("Story").objects.create(
            user=user, title="Alps", started=started
        )
        self._model("StoryEvent").objects.create(story=story, event=note)

        apps = self._migrate()

        story = apps.get_model("tree", "Story").objects.get(pk=story.pk)
        self.assertEqual(
            (story.event_stream.type, story.event_stream.created_by_id),
            ("trip", user.pk),
        )
        self.assertEqual(story.event_stream.created, started)
        self.assertEqual(
            list(story.event_stream.access.values_list("user_id", "role")),
            [(user.pk, "owner")],
        )
        self.assertEqual(
            set(
                apps.get_model("tree", "EventStreamEntry")
                .objects.filter(event_id=note.pk)
                .values_list("stream_id", flat=True)
            ),
            {daily.journal_stream_id, story.event_stream_id},
        )
