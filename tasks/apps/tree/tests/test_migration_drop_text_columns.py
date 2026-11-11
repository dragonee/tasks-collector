"""0103: the text columns go; reversed, they come back saying what the lines
say."""

import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0102_text_columns_as_copies")]
AFTER = [("tree", "0103_drop_text_columns")]

DAY = datetime.date(2026, 11, 10)


def _columns(table):
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table)
        }


class DropTextColumnsTestCase(TransactionTestCase):
    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def test_the_columns_go_and_come_back_from_the_lines(self):
        apps = self._migrate(AFTER)
        self.assertFalse({"focus"} & _columns("tree_plan"))
        self.assertFalse({"good", "better", "best"} & _columns("tree_reflection"))

        user = apps.get_model("common", "User").objects.create(username="u")
        EventStream = apps.get_model("tree", "EventStream")
        daily = apps.get_model("tree", "Thread").objects.create(
            user=user,
            name="Daily",
            board_stream=EventStream.objects.create(type="board", created_by=user),
            journal_stream=EventStream.objects.create(type="journal", created_by=user),
        )
        task = apps.get_model("tree", "Task").objects.create(
            user=user,
            text="call bank",
            anchor="0a1b2c3d",
            event_stream=daily.board_stream,
        )
        PlanLine = apps.get_model("tree", "PlanLine")
        ReflectionLine = apps.get_model("tree", "ReflectionLine")
        plan = apps.get_model("tree", "Plan").objects.create(thread=daily, pub_date=DAY)
        PlanLine.objects.create(plan=plan, position=0, task=task)
        PlanLine.objects.create(plan=plan, position=1, text="---")
        empty = apps.get_model("tree", "Plan").objects.create(
            thread=daily, pub_date=DAY + datetime.timedelta(days=1)
        )
        reflection = apps.get_model("tree", "Reflection").objects.create(
            thread=daily, pub_date=DAY
        )
        for position, (field, text) in enumerate(
            (("good", "a"), ("best", "c"), ("good", "b"))
        ):
            ReflectionLine.objects.create(
                reflection=reflection, field=field, position=position, text=text
            )

        apps = self._migrate(BEFORE)

        Plan = apps.get_model("tree", "Plan")
        self.assertEqual(Plan.objects.get(pk=plan.pk).focus_copy, "call bank\n---")
        self.assertIsNone(Plan.objects.get(pk=empty.pk).focus_copy)
        back = apps.get_model("tree", "Reflection").objects.get(pk=reflection.pk)
        self.assertEqual(
            (back.good_copy, back.better_copy, back.best_copy), ("a\nb", None, "c")
        )
