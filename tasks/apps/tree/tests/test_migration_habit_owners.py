"""0080-0082: existing habits, keywords and statistics get an owner,
profiles keep only their own user's keywords, and every user gets the
built-in poi and weight habits."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0080_habit_keyword_statistics_user")]
AFTER = [("tree", "0082_habit_keyword_statistics_user_required")]


class HabitOwnerMigrationTestCase(TransactionTestCase):
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
        User = self.old_apps.get_model("common", "User")
        user = User.objects.create(username=username)
        # As 0078 left every user: with a profile.
        self._model("Profile").objects.create(user=user)
        return user

    def _habit(self, slug, keywords=()):
        habit = self._model("Habit").objects.create(name=slug.title(), slug=slug)
        for keyword in keywords:
            self._model("HabitKeyword").objects.create(habit=habit, keyword=keyword)
        return habit

    def test_existing_habits_keywords_and_statistics_go_to_the_owner(self):
        owner = self._user("dragonee")
        food = self._habit("food", ["food", "jedzenie"])
        stat = self._model("Statistics").objects.create(key="total_word_count", value=5)

        apps = self._migrate()

        self.assertEqual(
            apps.get_model("tree", "Habit").objects.get(pk=food.pk).user_id, owner.pk
        )
        self.assertEqual(
            set(
                apps.get_model("tree", "HabitKeyword")
                .objects.filter(habit_id=food.pk)
                .values_list("user_id", flat=True)
            ),
            {owner.pk},
        )
        self.assertEqual(
            apps.get_model("tree", "Statistics").objects.get(pk=stat.pk).user_id,
            owner.pk,
        )

    def test_profiles_keep_only_their_own_users_keywords(self):
        owner = self._user("dragonee")
        other = self._user("other")
        food = self._habit("food", ["food"])
        food_keyword = food.keywords.get()
        # Every profile used to be given every keyword.
        for profile in self._model("Profile").objects.all():
            profile.habit_keywords.add(food_keyword)

        apps = self._migrate()

        Profile = apps.get_model("tree", "Profile")
        owners = set(
            Profile.objects.get(user_id=owner.pk).habit_keywords.values_list(
                "keyword", flat=True
            )
        )
        others = set(
            Profile.objects.get(user_id=other.pk).habit_keywords.values_list(
                "keyword", flat=True
            )
        )
        self.assertIn("food", owners)
        self.assertNotIn("food", others)
        # The other user's own built-in keywords are selected for them.
        self.assertIn("weight", others)

    def test_every_user_gets_builtin_habits_without_duplicates(self):
        owner = self._user("dragonee")
        other = self._user("other")
        poi = self._habit("poi", ["poi", "coords"])

        apps = self._migrate()

        Habit = apps.get_model("tree", "Habit")
        for user in (owner, other):
            slugs = Habit.objects.filter(user_id=user.pk).values_list("slug", flat=True)
            self.assertEqual(sorted(slugs), ["poi", "weight"])
        self.assertEqual(Habit.objects.get(user_id=owner.pk, slug="poi").pk, poi.pk)
        self.assertEqual(
            sorted(
                apps.get_model("tree", "HabitKeyword")
                .objects.filter(user_id=other.pk, habit__slug="poi")
                .values_list("keyword", flat=True)
            ),
            ["coordinates", "coords", "latlng", "poi"],
        )

    def test_without_users_the_seeded_habits_are_dropped(self):
        self._habit("poi", ["poi"])
        self._habit("weight", ["weight"])

        apps = self._migrate()

        self.assertFalse(apps.get_model("tree", "Habit").objects.exists())
        self.assertFalse(apps.get_model("tree", "HabitKeyword").objects.exists())
