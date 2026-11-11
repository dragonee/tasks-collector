"""0095-0097: journal tags get an owner. Everyone who tagged an entry with a
tag ends up with a tag of their own, carrying their entries."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

BEFORE = [("tree", "0094_event_created_by_set_null")]
AFTER = [("tree", "0097_journaltag_user_required")]


class JournalTagOwnerMigrationTestCase(TransactionTestCase):
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

    def _entry(self, user, *tags):
        """A diary entry of ``user`` carrying ``tags``, as the old code saved
        it (historical models don't run ``Thread.save`` or ``Event.save``)."""
        EventStream = self._model("EventStream")
        board = EventStream.objects.create(type="board", created_by=user)
        journal = EventStream.objects.create(type="journal", created_by=user)
        thread = self._model("Thread").objects.create(
            user=user,
            name=f"Daily {self._model('Thread').objects.count()}",
            board_stream=board,
            journal_stream=journal,
        )
        entry = self._model("JournalAdded").objects.create(
            thread=thread,
            event_stream=journal,
            created_by=user,
            comment="entry",
            published=timezone.now(),
        )
        for tag in tags:
            tag.journals.add(entry)
        return entry

    def _tag(self, slug):
        return self._model("JournalTag").objects.create(name=slug.title(), slug=slug)

    def _tags(self, apps, entry):
        JournalTag = apps.get_model("tree", "JournalTag")
        return sorted(
            JournalTag.objects.filter(journals=entry.pk).values_list(
                "user__username", "slug"
            )
        )

    def test_a_tag_only_the_owner_used_stays_with_the_owner(self):
        owner = self._user("dragonee")
        tag = self._tag("dreams")
        entry = self._entry(owner, tag)

        apps = self._migrate()

        JournalTag = apps.get_model("tree", "JournalTag")
        self.assertEqual(JournalTag.objects.get(pk=tag.pk).user_id, owner.pk)
        self.assertEqual(self._tags(apps, entry), [("dragonee", "dreams")])

    def test_everyone_who_used_a_tag_gets_their_own(self):
        owner = self._user("dragonee")
        other = self._user("karolina")
        tag = self._tag("thoughts")
        owners_entry = self._entry(owner, tag)
        others_entry = self._entry(other, tag)

        apps = self._migrate()

        JournalTag = apps.get_model("tree", "JournalTag")
        self.assertEqual(JournalTag.objects.get(pk=tag.pk).user_id, owner.pk)
        self.assertEqual(self._tags(apps, owners_entry), [("dragonee", "thoughts")])
        self.assertEqual(self._tags(apps, others_entry), [("karolina", "thoughts")])
        copy = JournalTag.objects.get(user_id=other.pk)
        self.assertEqual((copy.name, copy.slug), ("Thoughts", "thoughts"))

    def test_a_tag_only_another_user_used_goes_to_them(self):
        self._user("dragonee")
        other = self._user("karolina")
        tag = self._tag("garden")
        entry = self._entry(other, tag)

        apps = self._migrate()

        JournalTag = apps.get_model("tree", "JournalTag")
        self.assertEqual(JournalTag.objects.get(pk=tag.pk).user_id, other.pk)
        self.assertEqual(JournalTag.objects.count(), 1)
        self.assertEqual(self._tags(apps, entry), [("karolina", "garden")])

    def test_an_unused_tag_goes_to_the_owner(self):
        owner = self._user("dragonee")
        self._user("karolina")
        tag = self._tag("coverage")

        apps = self._migrate()

        JournalTag = apps.get_model("tree", "JournalTag")
        self.assertEqual(JournalTag.objects.get(pk=tag.pk).user_id, owner.pk)

    def test_without_users_unused_tags_are_dropped(self):
        self._tag("coverage")

        apps = self._migrate()

        self.assertFalse(apps.get_model("tree", "JournalTag").objects.exists())
