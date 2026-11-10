"""0077-0079: existing threads and breakthroughs get an owner, and every
existing user is provisioned with the built-in threads."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0077_thread_user_breakthrough_user")]
AFTER = [("tree", "0079_thread_user_breakthrough_user_required")]


class ThreadOwnerMigrationTestCase(TransactionTestCase):
    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(BEFORE)
        self.old_apps = self.executor.loader.project_state(BEFORE).apps

    def tearDown(self):
        # A test that stopped the migration leaves ownerless rows behind that
        # would stop it again on the way back to the latest schema.
        self._model("Thread").objects.filter(user__isnull=True).delete()
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

    def _user(self, username, **fields):
        User = self.old_apps.get_model("common", "User")
        return User.objects.create(username=username, **fields)

    def test_existing_threads_and_breakthroughs_go_to_the_owner(self):
        self._user("someone")
        owner = self._user("dragonee")
        Thread = self._model("Thread")
        daily = Thread.objects.create(name="Daily")
        sidetrack = Thread.objects.create(name="Sidetrack")
        breakthrough = self._model("Breakthrough").objects.create(slug="2026")

        apps = self._migrate()

        Thread = apps.get_model("tree", "Thread")
        self.assertEqual(Thread.objects.get(pk=daily.pk).user_id, owner.pk)
        self.assertEqual(Thread.objects.get(pk=sidetrack.pk).user_id, owner.pk)
        self.assertEqual(
            apps.get_model("tree", "Breakthrough")
            .objects.get(pk=breakthrough.pk)
            .user_id,
            owner.pk,
        )

    def test_without_the_named_owner_a_superuser_owns_them(self):
        self._user("plain")
        admin = self._user("admin", is_superuser=True)
        thread = self._model("Thread").objects.create(name="Daily")

        apps = self._migrate()

        self.assertEqual(
            apps.get_model("tree", "Thread").objects.get(pk=thread.pk).user_id, admin.pk
        )

    def test_every_user_is_provisioned_without_duplicating_existing_threads(self):
        owner = self._user("dragonee")
        newcomer = self._user("newcomer")
        Thread = self._model("Thread")
        daily = Thread.objects.create(name="Daily")
        self._model("Board").objects.create(thread=daily, focus="kept")

        apps = self._migrate()

        Thread = apps.get_model("tree", "Thread")
        Board = apps.get_model("tree", "Board")
        for user in (owner, newcomer):
            names = sorted(
                Thread.objects.filter(user_id=user.pk).values_list("name", flat=True)
            )
            self.assertEqual(names, ["Daily", "Weekly", "big-picture"])
            self.assertEqual(
                Board.objects.filter(thread__user_id=user.pk).count(), 3, user
            )
            self.assertTrue(
                apps.get_model("tree", "Profile")
                .objects.filter(user_id=user.pk)
                .exists()
            )
        # The owner's existing Daily thread and its board are reused.
        self.assertEqual(
            Thread.objects.get(user_id=owner.pk, name="Daily").pk, daily.pk
        )
        self.assertEqual(Board.objects.get(thread_id=daily.pk).focus, "kept")

    def test_new_profiles_get_all_habit_keywords(self):
        user = self._user("dragonee")
        habit = self._model("Habit").objects.create(name="Food", slug="food")
        keyword = self._model("HabitKeyword").objects.create(
            habit=habit, keyword="food"
        )

        apps = self._migrate()

        profile = apps.get_model("tree", "Profile").objects.get(user_id=user.pk)
        self.assertEqual(
            list(profile.habit_keywords.values_list("pk", flat=True)), [keyword.pk]
        )

    def test_threads_without_any_user_stop_the_migration(self):
        self._model("Thread").objects.create(name="Daily")

        with self.assertRaisesMessage(RuntimeError, "no user to own them"):
            self._migrate()

    def test_duplicate_thread_names_stop_the_migration(self):
        self._user("dragonee")
        Thread = self._model("Thread")
        Thread.objects.create(name="Daily")
        Thread.objects.create(name="Daily")

        with self.assertRaisesMessage(RuntimeError, "Several threads share a name"):
            self._migrate()
