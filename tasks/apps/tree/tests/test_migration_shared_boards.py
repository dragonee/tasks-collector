"""0093: a default board that is another user's thread becomes a board shared
with the profile's user; one that can't be shared (a built-in board) is
cleared."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0092_event_created_by_required")]
AFTER = [("tree", "0093_shared_boards")]


class SharedBoardsMigrationTestCase(TransactionTestCase):
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

    def _user(self, username):
        return self.old_apps.get_model("common", "User").objects.create(
            username=username
        )

    def _thread(self, user, name):
        """A thread with its two streams, as the old code saved it
        (historical models don't run ``Thread.save``)."""
        EventStream = self._model("EventStream")
        EventStreamAccess = self._model("EventStreamAccess")
        streams = {}
        for field, type_ in (("board_stream", "board"), ("journal_stream", "journal")):
            stream = EventStream.objects.create(type=type_, created_by=user)
            EventStreamAccess.objects.create(stream=stream, user=user, role="owner")
            streams[field] = stream
        return self._model("Thread").objects.create(user=user, name=name, **streams)

    def test_default_boards_of_other_users_become_shares(self):
        alice = self._user("alice")
        bob = self._user("bob")
        carol = self._user("carol")
        together = self._thread(alice, "Together")
        alices_daily = self._thread(alice, "Daily")
        Profile = self._model("Profile")
        Profile.objects.create(user=alice, default_board_thread=together)
        Profile.objects.create(user=bob, default_board_thread=together)
        Profile.objects.create(user=carol, default_board_thread=alices_daily)

        apps = self._migrate()

        EventStreamAccess = apps.get_model("tree", "EventStreamAccess")
        Profile = apps.get_model("tree", "Profile")
        self.assertEqual(
            sorted(
                EventStreamAccess.objects.filter(
                    stream_id=together.board_stream_id
                ).values_list("user__username", "role")
            ),
            [("alice", "owner"), ("bob", "editor")],
        )
        self.assertEqual(
            Profile.objects.get(user_id=bob.pk).default_board_thread_id, together.pk
        )
        self.assertEqual(
            Profile.objects.get(user_id=alice.pk).default_board_thread_id, together.pk
        )
        self.assertIsNone(Profile.objects.get(user_id=carol.pk).default_board_thread_id)
        self.assertFalse(
            EventStreamAccess.objects.filter(
                stream_id=alices_daily.board_stream_id, user_id=carol.pk
            ).exists()
        )
