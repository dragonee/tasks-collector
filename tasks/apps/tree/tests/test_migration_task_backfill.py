"""0101: every line of every plan and reflection gets a row, and the lines of
the plans whose period is not over become tasks."""

import datetime
from calendar import monthrange

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("tree", "0100_tasks")]
AFTER = [("tree", "0101_backfill_task_lines")]


def _item(item_id, text):
    return {
        "id": item_id,
        "text": text,
        "data": {"text": text, "state": "open", "taskId": None},
        "state": {"checked": False},
        "children": [],
    }


class TaskBackfillTestCase(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        self.old_apps = executor.loader.project_state(BEFORE).apps

        self.today = datetime.date.today()
        self.sunday = self.today + datetime.timedelta(days=6 - self.today.weekday())
        self.month_end = self.today.replace(
            day=monthrange(self.today.year, self.today.month)[1]
        )
        self.long_ago = self.today - datetime.timedelta(days=60)

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

    def _seed(self):
        Plan = self._model("Plan")
        Reflection = self._model("Reflection")

        self.alice = self._user("alice")
        self.daily = self._thread(self.alice, "Daily")
        self.weekly = self._thread(self.alice, "Weekly")
        self.big_picture = self._thread(self.alice, "big-picture")
        self.inbox = self._thread(self.alice, "Inbox")
        self._model("Profile").objects.create(
            user=self.alice, default_board_thread=self.inbox
        )
        self.board = self._model("Board").objects.create(
            thread=self.inbox,
            state=[
                _item("i-report", "write report"),
                _item("i-dup-1", "dup"),
                _item("i-dup-2", "dup"),
            ],
        )

        self.today_focus = "write report\r\n\r\n---\r\ncall bank\nDo x (3)\ndup\ndup"
        Plan.objects.create(
            thread=self.daily, pub_date=self.today, focus=self.today_focus
        )
        Plan.objects.create(
            thread=self.weekly, pub_date=self.sunday, focus="write report\ncall bank"
        )
        Plan.objects.create(
            thread=self.big_picture, pub_date=self.month_end, focus="write report"
        )
        Plan.objects.create(
            thread=self.daily, pub_date=self.long_ago, focus="old thing"
        )

        Reflection.objects.create(
            thread=self.daily,
            pub_date=self.today,
            good="call bank\nDo x (2)\nslept well",
            better="Do x (1)",
            best=None,
        )
        Reflection.objects.create(
            thread=self.daily, pub_date=self.long_ago, good="old thing"
        )

        # Someone who planned nothing.
        self.bob = self._user("bob")
        self._thread(self.bob, "Daily")

    def test_lines_and_tasks(self):
        self._seed()

        apps = self._migrate()
        Plan = apps.get_model("tree", "Plan")
        PlanLine = apps.get_model("tree", "PlanLine")
        Reflection = apps.get_model("tree", "Reflection")
        ReflectionLine = apps.get_model("tree", "ReflectionLine")
        Task = apps.get_model("tree", "Task")
        Board = apps.get_model("tree", "Board")

        # --- every document has its lines; the text columns are untouched
        today_plan = Plan.objects.get(thread_id=self.daily.pk, pub_date=self.today)
        self.assertEqual(today_plan.focus, self.today_focus)
        lines = list(PlanLine.objects.filter(plan=today_plan).order_by("position"))
        self.assertEqual(
            [line.text if line.task_id is None else line.task.text for line in lines],
            ["write report", "", "---", "call bank", "Do x (3)", "dup", "dup"],
        )
        # A blank line, a separator and a repeated line stay plain.
        self.assertEqual(
            [line.task_id is not None for line in lines],
            [True, False, False, True, True, True, False],
        )

        old_plan = Plan.objects.get(thread_id=self.daily.pk, pub_date=self.long_ago)
        (old_line,) = PlanLine.objects.filter(plan=old_plan)
        self.assertEqual((old_line.text, old_line.task_id), ("old thing", None))

        reflection = Reflection.objects.get(
            thread_id=self.daily.pk, pub_date=self.today
        )
        self.assertEqual(
            list(
                ReflectionLine.objects.filter(reflection=reflection)
                .order_by("field", "position")
                .values_list("field", "text")
            ),
            [
                ("better", "Do x (1)"),
                ("good", "call bank"),
                ("good", "Do x (2)"),
                ("good", "slept well"),
            ],
        )

        # --- the lines of the open periods are tasks; the same text is one
        tasks = {task.text: task for task in Task.objects.all()}
        self.assertEqual(
            sorted(tasks), ["Do x (3)", "call bank", "dup", "write report"]
        )
        for task in tasks.values():
            self.assertEqual(task.user_id, self.alice.pk)
            self.assertEqual(len(task.anchor), 8)
        self.assertEqual(len({task.anchor for task in tasks.values()}), 4)

        report = tasks["write report"]
        self.assertEqual(
            sorted(
                PlanLine.objects.filter(task=report).values_list(
                    "plan__thread__name", flat=True
                )
            ),
            ["Daily", "Weekly", "big-picture"],
        )
        self.assertEqual((report.done_count, report.completed_at), (0, None))

        # --- as done as the reflections of those periods say
        bank = tasks["call bank"]
        self.assertEqual(bank.done_count, 1)
        self.assertIsNotNone(bank.completed_at)
        counted = tasks["Do x (3)"]
        self.assertEqual((counted.done_count, counted.completed_at), (2, None))
        self.assertEqual(
            {
                line.text: line.task_id
                for line in ReflectionLine.objects.filter(reflection=reflection)
            },
            {
                "call bank": bank.pk,
                "Do x (1)": counted.pk,
                "Do x (2)": counted.pk,
                "slept well": None,
            },
        )

        # --- linked to the one board item of that text
        board = Board.objects.get(pk=self.board.pk)
        self.assertEqual(
            [item["data"]["taskId"] for item in board.state],
            [str(report.pk), None, None],
        )
        self.assertEqual(
            (report.board_id, report.board_item_id), (board.pk, "i-report")
        )
        self.assertIsNone(tasks["dup"].board_id)
        # In the stream of that board, or of the default board.
        for task in tasks.values():
            self.assertEqual(task.event_stream_id, self.inbox.board_stream_id)

    def test_going_back_unlinks_the_board_items(self):
        self._seed()
        self._migrate()

        apps = self._migrate(BEFORE)

        board = apps.get_model("tree", "Board").objects.get(pk=self.board.pk)
        self.assertEqual(
            [item["data"]["taskId"] for item in board.state], [None, None, None]
        )
        plan = apps.get_model("tree", "Plan").objects.get(
            thread_id=self.daily.pk, pub_date=self.today
        )
        self.assertEqual(plan.focus, self.today_focus)
