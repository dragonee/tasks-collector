"""0102: text written into a column behind its lines is brought into the
lines once more, before nothing reads the columns any longer."""

import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0101_backfill_task_lines")]
AFTER = [("tree", "0102_text_columns_as_copies")]

DAY = datetime.date(2026, 11, 10)


class CatchUpTestCase(TransactionTestCase):
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

    def _thread(self, user, name):
        """A thread with its two streams (historical models don't run
        ``Thread.save``)."""
        EventStream = self._model("EventStream")
        streams = {
            field: EventStream.objects.create(type=type_, created_by=user)
            for field, type_ in (
                ("board_stream", "board"),
                ("journal_stream", "journal"),
            )
        }
        return self._model("Thread").objects.create(user=user, name=name, **streams)

    def test_lines_catch_up_with_their_text(self):
        Plan = self._model("Plan")
        PlanLine = self._model("PlanLine")
        Reflection = self._model("Reflection")
        ReflectionLine = self._model("ReflectionLine")

        user = self.old_apps.get_model("common", "User").objects.create(username="u")
        daily = self._thread(user, "Daily")
        task = self._model("Task").objects.create(
            user=user,
            text="call bank",
            anchor="0a1b2c3d",
            event_stream=daily.board_stream,
        )

        in_step = Plan.objects.create(
            thread=daily, pub_date=DAY, focus="call bank\r\nwalk"
        )
        of_task = PlanLine.objects.create(plan=in_step, position=0, task=task)
        walk = PlanLine.objects.create(plan=in_step, position=1, text="walk")

        behind = Plan.objects.create(
            thread=daily,
            pub_date=DAY + datetime.timedelta(days=1),
            focus="call bank\nnew\nwalk",
        )
        kept = PlanLine.objects.create(plan=behind, position=0, task=task)
        PlanLine.objects.create(plan=behind, position=1, text="gone")
        PlanLine.objects.create(plan=behind, position=2, text="walk")

        reflection = Reflection.objects.create(
            thread=daily, pub_date=DAY, good="call bank", better="start earlier"
        )
        done = ReflectionLine.objects.create(
            reflection=reflection, field="good", position=0, text="call bank", task=task
        )

        apps = self._migrate()
        PlanLine = apps.get_model("tree", "PlanLine")
        ReflectionLine = apps.get_model("tree", "ReflectionLine")

        def lines(plan):
            return list(
                PlanLine.objects.filter(plan_id=plan.pk)
                .order_by("position")
                .values_list("pk", "task_id", "text")
            )

        # A document whose lines say what its text says is left as it is.
        self.assertEqual(
            lines(in_step), [(of_task.pk, task.pk, ""), (walk.pk, None, "walk")]
        )
        # The others get the lines of their text; those still there stay,
        # with their tasks.
        self.assertEqual(
            [(task_id, text) for _pk, task_id, text in lines(behind)],
            [(task.pk, ""), (None, "new"), (None, "walk")],
        )
        self.assertEqual(lines(behind)[0][0], kept.pk)
        self.assertEqual(
            list(
                ReflectionLine.objects.filter(reflection_id=reflection.pk)
                .order_by("field", "position")
                .values_list("pk", "field", "text", "task_id")
            )[1:],
            [(done.pk, "good", "call bank", task.pk)],
        )
        self.assertEqual(
            ReflectionLine.objects.get(field="better").text, "start earlier"
        )

        # The columns are where they were, under their new names.
        plan = apps.get_model("tree", "Plan").objects.get(pk=in_step.pk)
        self.assertEqual(plan.focus_copy, "call bank\r\nwalk")
