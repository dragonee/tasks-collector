"""0090-0092: existing events are credited to the user who started their
stream."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

BEFORE = [("tree", "0090_event_created_by")]
AFTER = [("tree", "0092_event_created_by_required")]


class CreatedByBackfillTestCase(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        self.old_apps = executor.loader.project_state(BEFORE).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_events_are_credited_to_their_streams_creator(self):
        model = lambda name: self.old_apps.get_model("tree", name)
        user = self.old_apps.get_model("common", "User").objects.create(
            username="dragonee"
        )
        streams = [
            model("EventStream").objects.create(type=t, created_by=user)
            for t in ("board", "journal")
        ]
        daily = model("Thread").objects.create(
            user=user, name="Daily", board_stream=streams[0], journal_stream=streams[1]
        )
        ContentType = self.old_apps.get_model("contenttypes", "ContentType")
        journal = model("JournalAdded").objects.create(
            thread=daily,
            event_stream=streams[1],
            comment="hello",
            published=timezone.now(),
            polymorphic_ctype=ContentType.objects.get_or_create(
                app_label="tree", model="journaladded"
            )[0],
        )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps

        self.assertEqual(
            apps.get_model("tree", "Event").objects.get(pk=journal.pk).created_by_id,
            user.pk,
        )
