"""0110: each user's roles are filled by the habits that played them, and the
entries the phones wrote for them become the roles'."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0109_habit_roles")]
AFTER = [("tree", "0110_fill_habit_roles")]


class FillHabitRolesMigrationTestCase(TransactionTestCase):
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

    def _habit(self, user, slug, keywords=()):
        habit = self._model("Habit").objects.create(
            user=user, name=slug, slug=slug, event_stream=self._stream(user, "habit")
        )
        for keyword in keywords:
            self._model("HabitKeyword").objects.create(
                habit=habit, user=user, keyword=keyword
            )
        return habit

    def _tracked(self, habit, note):
        return self._model("HabitTracked").objects.create(
            habit=habit,
            note=note,
            thread=habit.user.daily,
            event_stream_id=habit.event_stream_id,
            created_by=habit.user,
        )

    def test_roles_from_slugs_and_keywords_and_the_phones_entries_marked(self):
        alice = self._user("alice")
        breakthrough = self._habit(alice, "breakthrough")
        weight = self._habit(alice, "weight", ["weight"])
        health = self._habit(alice, "health", ["health", "health-metrics"])
        workout = self._habit(alice, "workout", ["workout", "running"])
        synced = self._tracked(health, "steps=5000 distance=3.5km active=80min kcal=2")
        by_hand = self._tracked(health, "#health doctor (pressure=120/80)")
        ride = self._tracked(workout, "#workout Bike ride (duration=45m)")
        run = self._tracked(workout, "#running (distance=5km)")
        bob = self._user("bob")
        self._habit(bob, "weight", ["weight"])

        apps = self._migrate()
        HabitRole = apps.get_model("tree", "HabitRole")
        HabitTracked = apps.get_model("tree", "HabitTracked")

        self.assertEqual(
            set(
                HabitRole.objects.filter(user_id=alice.pk).values_list(
                    "role", "habit_id"
                )
            ),
            {
                ("breakthrough", breakthrough.pk),
                ("weight", weight.pk),
                ("daily-health", health.pk),
                ("bike-ride", workout.pk),
            },
        )
        self.assertEqual(
            list(
                HabitRole.objects.filter(user_id=bob.pk).values_list("role", flat=True)
            ),
            ["weight"],
        )

        def role(entry):
            return HabitTracked.objects.get(pk=entry.pk).role

        self.assertEqual(role(synced), "daily-health")
        self.assertEqual(role(by_hand), "")
        self.assertEqual(role(ride), "bike-ride")
        self.assertEqual(role(run), "")

    def test_reversing_empties_the_roles_and_the_marks(self):
        alice = self._user("alice")
        health = self._habit(alice, "health", ["health-metrics"])
        synced = self._tracked(health, "steps=5000")

        self._migrate()
        apps = self._migrate(BEFORE)

        self.assertFalse(apps.get_model("tree", "HabitRole").objects.exists())
        self.assertEqual(
            apps.get_model("tree", "HabitTracked").objects.get(pk=synced.pk).role, ""
        )
