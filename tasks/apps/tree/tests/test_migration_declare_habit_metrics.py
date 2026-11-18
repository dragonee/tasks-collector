"""0108: each habit declares the metrics its notes carry, and every entry gets
the values they give."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0107_habit_metrics")]
AFTER = [("tree", "0108_declare_habit_metrics")]


class DeclareHabitMetricsMigrationTestCase(TransactionTestCase):
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

    def _user(self, username):
        user = self.old_apps.get_model("common", "User").objects.create(
            username=username
        )
        user.daily = self._model("Thread").objects.create(
            user=user,
            name="Daily",
            board_stream=self._stream(user, "board"),
            journal_stream=self._stream(user, "journal"),
        )
        return user

    def _habit(self, user, slug, *notes):
        habit = self._model("Habit").objects.create(
            user=user, name=slug, slug=slug, event_stream=self._stream(user, "habit")
        )
        habit.entries = [
            self._model("HabitTracked").objects.create(
                habit=habit,
                note=note,
                thread=user.daily,
                event_stream_id=habit.event_stream_id,
                created_by=user,
            )
            for note in notes
        ]
        return habit

    def test_metrics_come_from_the_tokens_and_entries_get_their_values(self):
        alice = self._user("alice")
        health = self._habit(
            alice,
            "health",
            "steps=5000 distance=3.5km active=80min kcal=2000",
            "steps=6000 distance=4km active=90min kcal=2100",
            "#health 120/80 (pressure=120/80)",
        )
        workout = self._habit(
            alice, "workout", "#running distance=3.0km, duration=22m30s"
        )
        spent = self._habit(
            alice, "spent", "#spent 45zł (amount=45PLN)", "#spent (amount=90EUR)"
        )
        poi = self._habit(alice, "poi", "#poi lat=52.1 lng=21.0")
        til = self._habit(alice, "til", "#til https://example.com/watch?v=4dSL")
        weight = self._habit(alice, "weight")

        apps = self._migrate()
        HabitMetric = apps.get_model("tree", "HabitMetric")
        HabitTracked = apps.get_model("tree", "HabitTracked")

        def declared(habit):
            return list(
                HabitMetric.objects.filter(habit_id=habit.pk)
                .order_by("order")
                .values_list("key", "kind", "unit", "decimals")
            )

        self.assertEqual(
            declared(health),
            [
                ("steps", "number", "", 0),
                ("distance", "number", "km", 1),
                ("active", "number", "min", 0),
                ("kcal", "number", "", 0),
                ("pressure", "pressure", "", 0),
            ],
        )
        self.assertEqual(
            declared(workout),
            [("distance", "number", "km", 1), ("duration", "duration", "", 0)],
        )
        self.assertEqual(declared(spent), [("amount", "money", "", 0)])
        self.assertEqual(declared(poi), [])
        self.assertEqual(declared(til), [])
        self.assertEqual(declared(weight), [("weight", "number", "kg", 1)])

        def values(entry):
            return HabitTracked.objects.get(pk=entry.pk).values

        self.assertEqual(
            values(health.entries[0]),
            {"steps": 5000, "distance": 3.5, "active": 80, "kcal": 2000},
        )
        self.assertEqual(values(health.entries[2]), {"pressure": [120, 80]})
        self.assertEqual(values(workout.entries[0]), {"distance": 3, "duration": 1350})
        self.assertEqual(
            values(spent.entries[1]), {"amount": {"amount": 90, "currency": "EUR"}}
        )
        self.assertEqual(values(poi.entries[0]), {})

    def test_reversing_takes_the_metrics_and_values_away(self):
        alice = self._user("alice")
        health = self._habit(alice, "health", "steps=5000")

        self._migrate()
        apps = self._migrate(BEFORE)

        self.assertFalse(apps.get_model("tree", "HabitMetric").objects.exists())
        self.assertEqual(
            apps.get_model("tree", "HabitTracked")
            .objects.get(pk=health.entries[0].pk)
            .values,
            {},
        )
