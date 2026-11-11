"""0098: every board item gets an id of its own, an empty task link and one
answer to "is it ticked?". 0099: a thread has one plan and one reflection per
date."""

import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0097_journaltag_user_required")]
SHAPED = [("tree", "0098_board_item_shape")]
UNIQUE = [("tree", "0099_plan_reflection_unique")]


class _MigrationTestCase(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        self.old_apps = executor.loader.project_state(BEFORE).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def _model(self, name):
        return self.old_apps.get_model("tree", name)

    def _thread(self, name="Inbox"):
        """A thread with its two streams, as the old code saved it
        (historical models don't run ``Thread.save``)."""
        user = self.old_apps.get_model("common", "User").objects.create(username=name)
        EventStream = self._model("EventStream")
        EventStreamAccess = self._model("EventStreamAccess")
        streams = {}
        for field, type_ in (("board_stream", "board"), ("journal_stream", "journal")):
            stream = EventStream.objects.create(type=type_, created_by=user)
            EventStreamAccess.objects.create(stream=stream, user=user, role="owner")
            streams[field] = stream
        return self._model("Thread").objects.create(user=user, name=name, **streams)


class BoardItemShapeMigrationTestCase(_MigrationTestCase):
    def test_items_get_ids_task_links_and_one_done_state(self):
        board = self._model("Board").objects.create(
            thread=self._thread(),
            state=[
                # Made on the web long ago: no id, ticked in state.checked only.
                {
                    "text": "old",
                    "data": {"text": "old", "state": "open", "meaningfulMarkers": {}},
                    "state": {"checked": True, "expanded": False},
                    "children": [
                        {
                            "text": "child",
                            "data": {"text": "child", "state": "open"},
                            "children": [],
                        }
                    ],
                },
                # Appended by the Android app: an id, no top-level state.
                {
                    "id": "keep-me",
                    "text": "new",
                    "data": {"text": "new", "state": "done"},
                    "children": [],
                },
                # The same id twice on one board.
                {"id": "keep-me", "text": "copy", "data": {}, "children": []},
            ],
        )

        Board = self._migrate(SHAPED).get_model("tree", "Board")

        old, new, copy = Board.objects.get(pk=board.pk).state
        (child,) = old["children"]

        self.assertEqual(new["id"], "keep-me")
        ids = [old["id"], child["id"], new["id"], copy["id"]]
        self.assertTrue(all(ids))
        self.assertEqual(len(set(ids)), 4)

        for item in (old, child, new, copy):
            self.assertIsNone(item["data"]["taskId"])

        self.assertEqual(old["data"]["state"], "done")
        self.assertEqual(old["state"], {"checked": True, "expanded": False})
        self.assertEqual(child["data"]["state"], "open")
        self.assertEqual(child["state"], {"checked": False})
        self.assertEqual(new["state"], {"checked": True})
        self.assertEqual(old["data"]["text"], "old")


class PlanReflectionUniqueMigrationTestCase(_MigrationTestCase):
    def test_duplicates_are_merged_into_the_oldest(self):
        thread = self._thread()
        other = self._thread("Other")
        day = datetime.date(2026, 11, 11)
        Plan = self._model("Plan")
        Reflection = self._model("Reflection")

        first = Plan.objects.create(thread=thread, pub_date=day, focus="a")
        Plan.objects.create(thread=thread, pub_date=day, focus=None)
        Plan.objects.create(thread=thread, pub_date=day, focus="b\nc")
        Plan.objects.create(thread=other, pub_date=day, focus="theirs")
        Plan.objects.create(
            thread=thread, pub_date=day + datetime.timedelta(days=1), focus="next"
        )

        kept = Reflection.objects.create(thread=thread, pub_date=day, good="g1")
        Reflection.objects.create(thread=thread, pub_date=day, good="g2", best="top")

        apps = self._migrate(UNIQUE)
        Plan = apps.get_model("tree", "Plan")
        Reflection = apps.get_model("tree", "Reflection")

        plan = Plan.objects.get(thread_id=thread.pk, pub_date=day)
        self.assertEqual(plan.pk, first.pk)
        self.assertEqual(plan.focus, "a\nb\nc")
        self.assertEqual(Plan.objects.count(), 3)

        reflection = Reflection.objects.get(thread_id=thread.pk, pub_date=day)
        self.assertEqual(reflection.pk, kept.pk)
        self.assertEqual(reflection.good, "g1\ng2")
        self.assertIsNone(reflection.better)
        self.assertEqual(reflection.best, "top")
