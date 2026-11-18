"""0112: a trip note's or photo's place line becomes its EventLocation and
leaves the comment; reversing puts the line back."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0111_event_location")]
AFTER = [("tree", "0112_places_from_comments")]


class PlacesFromCommentsMigrationTestCase(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        self.old_apps = executor.loader.project_state(BEFORE).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, target=AFTER):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def _model(self, name):
        return self.old_apps.get_model("tree", name)

    def _stream(self, user, type_):
        stream = self._model("EventStream").objects.create(type=type_, created_by=user)
        self._model("EventStreamAccess").objects.create(
            stream=stream, user=user, role="owner"
        )
        return stream

    def _entries(self, *comments):
        user = self.old_apps.get_model("common", "User").objects.create(
            username="alice"
        )
        daily = self._model("Thread").objects.create(
            user=user,
            name="Daily",
            board_stream=self._stream(user, "board"),
            journal_stream=self._stream(user, "journal"),
        )
        return [
            self._model("JournalAdded").objects.create(
                thread=daily,
                comment=comment,
                event_stream_id=daily.journal_stream_id,
                created_by=user,
            )
            for comment in comments
        ]

    def test_place_lines_become_locations(self):
        note, photo_only, plain, inside = self._entries(
            "#poi lat=38.7139 lng=-9.1335\nMiradouro",
            "#poi lat=10 lng=20 acc=5",
            "Just a walk",
            "Saw a #poi sign\n#poi lat=1 lng=2",
        )

        apps = self._migrate()
        JournalAdded = apps.get_model("tree", "JournalAdded")
        EventLocation = apps.get_model("tree", "EventLocation")

        def after(entry):
            location = EventLocation.objects.filter(event_id=entry.pk).first()
            where = (location.lat, location.lng, location.acc) if location else None
            return JournalAdded.objects.get(pk=entry.pk).comment, where

        self.assertEqual(after(note), ("Miradouro", (38.7139, -9.1335, None)))
        self.assertEqual(after(photo_only), ("", (10.0, 20.0, 5.0)))
        self.assertEqual(after(plain), ("Just a walk", None))
        self.assertEqual(after(inside), ("Saw a #poi sign\n#poi lat=1 lng=2", None))

    def test_reversing_puts_the_lines_back_but_not_over_a_change(self):
        note, changed = self._entries(
            "#poi lat=38.7 lng=-9.1\nMiradouro", "#poi lat=1 lng=2\nfirst"
        )
        apps = self._migrate()
        apps.get_model("tree", "JournalAdded").objects.filter(pk=changed.pk).update(
            comment="edited since"
        )

        apps = self._migrate(BEFORE)
        JournalAdded = apps.get_model("tree", "JournalAdded")

        self.assertEqual(
            JournalAdded.objects.get(pk=note.pk).comment,
            "#poi lat=38.7 lng=-9.1\nMiradouro",
        )
        self.assertEqual(
            JournalAdded.objects.get(pk=changed.pk).comment, "edited since"
        )
        self.assertFalse(apps.get_model("tree", "EventLocation").objects.exists())
