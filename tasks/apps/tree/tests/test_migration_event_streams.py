"""0083-0085: every stream id in use becomes an EventStream row with its
id, type and owner; every thread gets its board and journal stream."""

import uuid

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from ..migrations._legacy_stream_ids import (
    BOARD_URL,
    JOURNAL_URL,
    thread_event_stream_id,
)

BEFORE = [("tree", "0083_eventstream")]
AFTER = [("tree", "0085_event_stream_links_required")]


class EventStreamBackfillTestCase(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        self.old_apps = executor.loader.project_state(BEFORE).apps

    def tearDown(self):
        # Events a stopped migration couldn't type would stop it again on the
        # way back to the latest schema; the test database is flushed anyway.
        self._model("Event").objects.all().delete()
        ContentType = self.old_apps.get_model("contenttypes", "ContentType")
        ContentType.objects.filter(app_label="tree", model="discovery").delete()
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

    def _user(self, username):
        return self.old_apps.get_model("common", "User").objects.create(
            username=username
        )

    def _event(self, model, thread, stream_id, **fields):
        """An event as the old code saved it (historical models are not
        polymorphic, so the content type is set by hand)."""
        ContentType = self.old_apps.get_model("contenttypes", "ContentType")
        ctype, _ = ContentType.objects.get_or_create(
            app_label="tree", model=model.lower()
        )
        return self._model(model).objects.create(
            thread=thread,
            event_stream_id=stream_id,
            polymorphic_ctype=ctype,
            published=timezone.now(),
            **fields,
        )

    def test_threads_keep_their_stream_ids(self):
        user = self._user("dragonee")
        daily = self._model("Thread").objects.create(user=user, name="Daily")
        journal_id = thread_event_stream_id(JOURNAL_URL, daily)
        entry = self._event("JournalAdded", daily, journal_id, comment="hi")

        apps = self._migrate()

        thread = apps.get_model("tree", "Thread").objects.get(pk=daily.pk)
        self.assertEqual(thread.journal_stream_id, journal_id)
        self.assertEqual(
            thread.board_stream_id, thread_event_stream_id(BOARD_URL, daily)
        )
        self.assertEqual(thread.journal_stream.type, "journal")
        self.assertEqual(thread.journal_stream.created_by_id, user.pk)
        self.assertEqual(
            apps.get_model("tree", "Event").objects.get(pk=entry.pk).event_stream_id,
            journal_id,
        )

    def test_threads_that_shared_an_id_get_their_own(self):
        Thread = self._model("Thread")
        first = Thread.objects.create(user=self._user("dragonee"), name="Daily")
        second = Thread.objects.create(user=self._user("other"), name="Daily")
        shared = thread_event_stream_id(JOURNAL_URL, first)
        firsts = self._event("JournalAdded", first, shared, comment="mine")
        seconds = self._event("JournalAdded", second, shared, comment="theirs")

        apps = self._migrate()

        Thread = apps.get_model("tree", "Thread")
        Event = apps.get_model("tree", "Event")
        first, second = Thread.objects.get(pk=first.pk), Thread.objects.get(
            pk=second.pk
        )
        self.assertEqual(first.journal_stream_id, shared)
        self.assertNotEqual(second.journal_stream_id, shared)
        self.assertEqual(Event.objects.get(pk=firsts.pk).event_stream_id, shared)
        self.assertEqual(
            Event.objects.get(pk=seconds.pk).event_stream_id, second.journal_stream_id
        )
        self.assertEqual(second.journal_stream.created_by_id, second.user_id)

    def test_board_commits_filed_under_another_threads_stream_follow_their_thread(
        self,
    ):
        user = self._user("dragonee")
        Thread = self._model("Thread")
        weekly = Thread.objects.create(user=user, name="Weekly")
        big_picture = Thread.objects.create(user=user, name="big-picture")
        misfiled = self._event(
            "BoardCommitted",
            weekly,
            thread_event_stream_id(BOARD_URL, big_picture),
            focus="",
        )

        apps = self._migrate()

        self.assertEqual(
            apps.get_model("tree", "Event").objects.get(pk=misfiled.pk).event_stream_id,
            apps.get_model("tree", "Thread").objects.get(pk=weekly.pk).board_stream_id,
        )

    def test_closed_observation_streams_are_owned_by_their_threads_user(self):
        user = self._user("dragonee")
        daily = self._model("Thread").objects.create(user=user, name="Daily")
        obs_type = self._model("ObservationType").objects.create(name="E", slug="e")
        closed_id = uuid.uuid4()
        self._event("ObservationClosed", daily, closed_id, type=obs_type)
        journalized_id = uuid.uuid4()
        self._event(
            "ObservationAttached",
            daily,
            closed_id,
            other_event_stream_id=journalized_id,
        )

        apps = self._migrate()

        EventStream = apps.get_model("tree", "EventStream")
        for stream_id in (closed_id, journalized_id):
            stream = EventStream.objects.get(pk=stream_id)
            self.assertEqual(
                (stream.type, stream.created_by_id), ("observation", user.pk)
            )
            self.assertEqual(
                list(stream.access.values_list("user_id", "role")),
                [(user.pk, "owner")],
            )

    def test_open_observations_link_to_their_stream(self):
        user = self._user("dragonee")
        daily = self._model("Thread").objects.create(user=user, name="Daily")
        obs_type = self._model("ObservationType").objects.create(name="E", slug="e")
        observation = self._model("Observation").objects.create(
            user=user, thread=daily, type=obs_type, pub_date=timezone.now().date()
        )

        apps = self._migrate()

        observation = apps.get_model("tree", "Observation").objects.get(
            pk=observation.pk
        )
        self.assertEqual(observation.event_stream.type, "observation")

    def test_events_of_unknown_kinds_stop_the_migration(self):
        user = self._user("dragonee")
        daily = self._model("Thread").objects.create(user=user, name="Daily")
        ContentType = self.old_apps.get_model("contenttypes", "ContentType")
        discovery = ContentType.objects.create(app_label="tree", model="discovery")
        self._model("Event").objects.create(
            thread=daily,
            event_stream_id=uuid.uuid4(),
            polymorphic_ctype=discovery,
            published=timezone.now(),
        )

        with self.assertRaisesMessage(RuntimeError, "Events of unknown kinds"):
            self._migrate()

    def test_streams_mixing_kinds_stop_the_migration(self):
        user = self._user("dragonee")
        daily = self._model("Thread").objects.create(user=user, name="Daily")
        shared = uuid.uuid4()
        obs_type = self._model("ObservationType").objects.create(name="E", slug="e")
        self._event("ObservationMade", daily, shared, type=obs_type)
        habit = self._model("Habit").objects.create(user=user, name="F", slug="f")
        self._event("HabitTracked", daily, shared, habit=habit)

        with self.assertRaisesMessage(RuntimeError, "mixing kinds"):
            self._migrate()
