"""The API by task id (api/v1/tasks/), and what else names a task by id or
anchor: plans/add-task/, the board picker, journal lines."""

import datetime
import threading

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase

from ..board_operations import create_unscheduled_task
from ..models import (
    Board,
    JournalAdded,
    Plan,
    Reflection,
    ReflectionLine,
    Task,
    TaskCompleted,
    Thread,
)
from ..services.streams import share
from ..services.tasks import operations as tasks
from ..services.today import plan_text
from ..services.today.operations import lock_day
from ..services.trips import start_trip, stop_trip
from .factories import (
    make_board,
    make_plan,
    make_profile,
    make_thread,
    plan_task,
    trip_links,
)

DAY = datetime.date(2026, 6, 25)  # a Thursday
SUNDAY = datetime.date(2026, 6, 28)
MONTH_END = datetime.date(2026, 6, 30)
AT = "2026-06-25T21:30:00+02:00"


class TaskAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.daily(cls.user)
        cls.weekly = make_thread(cls.user, "Weekly")
        cls.inbox = make_thread(cls.user, "Inbox")
        make_profile(cls.user, default_board_thread=cls.inbox)
        cls.board = make_board(
            thread=cls.inbox,
            state=[create_unscheduled_task("water plants")],
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _post(self, name, data=None, **kwargs):
        return self.client.post(reverse(name, kwargs=kwargs), data or {}, format="json")

    def _create(self, **data):
        response = self._post("task-create", {"date": DAY.isoformat(), **data})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return response.json()

    def _agenda(self, day=DAY):
        response = self.client.get(reverse("task-agenda"), {"date": day.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()

    def _item(self):
        return Board.objects.get(pk=self.board.pk).state[0]


class CreateAndAgendaTestCase(TaskAPITestCase):
    def test_a_typed_task(self):
        task = self._create(text="call bank")

        self.assertEqual(
            task,
            {
                "id": task["id"],
                "anchor": Task.objects.get().anchor,
                "text": "call bank",
                "display": "call bank",
                "done": False,
                "mark": None,
                "total": 1,
                "done_count": 0,
                "completed_at": None,
                "board": None,
                "plans": [{"thread": "Daily", "pub_date": DAY.isoformat()}],
            },
        )
        self.assertEqual(Plan.objects.get().focus, "call bank")
        # Not written to the board.
        self.assertEqual(len(Board.objects.get(pk=self.board.pk).state), 1)

    def test_the_same_text_again_is_the_same_task(self):
        first = self._create(text="call bank")
        again = self._create(text="call bank")
        in_the_week = self._create(text="call bank", thread="Weekly")

        self.assertEqual(first["id"], again["id"])
        self.assertEqual(in_the_week["id"], first["id"])
        self.assertEqual(
            in_the_week["plans"],
            [
                {"thread": "Daily", "pub_date": DAY.isoformat()},
                {"thread": "Weekly", "pub_date": SUNDAY.isoformat()},
            ],
        )

    def test_a_board_item(self):
        item = self._item()

        task = self._create(board_id=self.board.pk, item_id=item["id"])

        self.assertEqual(task["text"], "water plants")
        self.assertEqual(
            task["board"],
            {"id": self.board.pk, "item_id": item["id"], "thread": "Inbox"},
        )
        self.assertEqual(self._item()["data"]["taskId"], task["id"])
        # Planning it again, for the week, is the same task.
        again = self._create(
            board_id=self.board.pk, item_id=item["id"], thread="Weekly"
        )
        self.assertEqual(again["id"], task["id"])

    def test_an_item_that_is_not_there_is_not_found(self):
        for data in (
            {"board_id": self.board.pk, "item_id": "nope"},
            {"board_id": 999999, "item_id": self._item()["id"]},
        ):
            with self.subTest(data=data):
                response = self._post("task-create", {"date": DAY.isoformat(), **data})
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Task.objects.exists())

    def test_what_to_plan_and_when_are_required(self):
        for data in (
            {"text": "x"},
            {"date": DAY.isoformat()},
            {"date": DAY.isoformat(), "text": "x", "board_id": 1, "item_id": "1"},
            {"date": DAY.isoformat(), "text": "x", "thread": "Inbox"},
            {"date": "yesterday", "text": "x"},
        ):
            with self.subTest(data=data):
                response = self._post("task-create", data)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Task.objects.exists())

    def test_the_agenda_is_the_day_the_week_and_the_month(self):
        day_task = self._create(text="call bank")
        week_task = self._create(text="write report (2)", thread="Weekly")
        make_plan(
            Thread.objects.get(user=self.user, name="big-picture"),
            MONTH_END,
            "a theme, written long ago",
        )

        agenda = self._agenda()

        self.assertEqual(agenda["date"], DAY.isoformat())
        self.assertEqual(
            {
                key: (agenda[key]["thread"], agenda[key]["pub_date"])
                for key in agenda
                if key != "date"
            },
            {
                "daily": ("Daily", DAY.isoformat()),
                "weekly": ("Weekly", SUNDAY.isoformat()),
                "monthly": ("big-picture", MONTH_END.isoformat()),
            },
        )
        self.assertEqual(agenda["daily"]["tasks"], [day_task])
        (in_the_week,) = agenda["weekly"]["tasks"]
        self.assertEqual(in_the_week["id"], week_task["id"])
        self.assertEqual(
            (in_the_week["text"], in_the_week["display"], in_the_week["total"]),
            ("write report (2)", "write report (1/2)", 2),
        )
        # A plain line has no id.
        (plain,) = agenda["monthly"]["tasks"]
        self.assertEqual(
            (plain["id"], plain["text"], plain["plans"]),
            (None, "a theme, written long ago", []),
        )

    def test_the_agenda_needs_a_date(self):
        response = self.client.get(reverse("task-agenda"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_agenda_costs_the_same_for_one_task_or_many(self):
        # One of each kind: typed, of the week, from the board, done.
        self._create(text="one")
        self._create(text="week task", thread="Weekly")
        from_board = self._create(board_id=self.board.pk, item_id=self._item()["id"])
        self._post("task-complete", {"day": DAY.isoformat()}, task_id=from_board["id"])
        with CaptureQueriesContext(connection) as few:
            self._agenda()

        for number in range(8):
            task = self._create(text=f"task {number}")
            self._create(text=f"week task {number}", thread="Weekly")
            self._post("task-complete", {"day": DAY.isoformat()}, task_id=task["id"])
        with CaptureQueriesContext(connection) as many:
            self._agenda()

        self.assertEqual(len(many), len(few))


class ChangeTestCase(TaskAPITestCase):
    def test_rename_reads_so_everywhere(self):
        item = self._item()
        task = self._create(board_id=self.board.pk, item_id=item["id"])
        self._create(board_id=self.board.pk, item_id=item["id"], thread="Weekly")

        response = self.client.patch(
            reverse("task-detail", kwargs={"task_id": task["id"]}),
            {"text": "water the plants"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["text"], "water the plants")
        self.assertEqual(
            [plan.focus for plan in Plan.objects.all()], ["water the plants"] * 2
        )
        self.assertEqual(self._item()["text"], "water the plants")
        self.assertEqual(self._item()["data"]["text"], "water the plants")

    def test_a_task_is_one_line(self):
        task = self._create(text="call bank")

        for text in ("", "two\nlines"):
            with self.subTest(text=text):
                response = self.client.patch(
                    reverse("task-detail", kwargs={"task_id": task["id"]}),
                    {"text": text},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plan_move_and_unplan(self):
        task = self._create(text="call bank")
        friday = DAY + datetime.timedelta(days=1)

        planned = self._post(
            "task-plan",
            {"thread": "Weekly", "date": DAY.isoformat()},
            task_id=task["id"],
        ).json()
        self.assertEqual(len(planned["plans"]), 2)

        moved = self._post(
            "task-move",
            {"from_date": DAY.isoformat(), "to_date": friday.isoformat()},
            task_id=task["id"],
        ).json()
        self.assertEqual(
            moved["plans"],
            [
                {"thread": "Daily", "pub_date": friday.isoformat()},
                {"thread": "Weekly", "pub_date": SUNDAY.isoformat()},
            ],
        )
        self.assertEqual(self._agenda()["daily"]["tasks"], [])

        off_the_week = self._post(
            "task-unplan",
            {"thread": "Weekly", "date": DAY.isoformat()},
            task_id=task["id"],
        )
        self.assertEqual(off_the_week.status_code, status.HTTP_200_OK)
        self.assertEqual(len(off_the_week.json()["plans"]), 1)

        # Off its last plan, never done, no board item: nothing remembers it.
        gone = self._post(
            "task-unplan", {"date": friday.isoformat()}, task_id=task["id"]
        )
        self.assertEqual(gone.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.exists())

    def test_complete_and_reopen(self):
        item = self._item()
        task = self._create(board_id=self.board.pk, item_id=item["id"])

        done = self._post(
            "task-complete", {"day": DAY.isoformat(), "at": AT}, task_id=task["id"]
        )

        self.assertEqual(done.status_code, status.HTTP_200_OK)
        self.assertEqual((done.json()["done"], done.json()["done_count"]), (True, 1))
        self.assertIsNotNone(done.json()["completed_at"])
        completion = TaskCompleted.objects.get()
        self.assertEqual(completion.day, DAY)
        self.assertEqual(Reflection.objects.get(pub_date=DAY).good, "water plants")
        self.assertTrue(self._item()["state"]["checked"])
        self.assertEqual(self._agenda()["daily"]["tasks"][0]["done"], True)

        reopened = self._post("task-reopen", task_id=task["id"])

        self.assertEqual(reopened.status_code, status.HTTP_200_OK)
        self.assertEqual(
            (reopened.json()["done"], reopened.json()["done_count"]), (False, 0)
        )
        self.assertFalse(TaskCompleted.objects.exists())
        self.assertEqual(Reflection.objects.get(pub_date=DAY).good, "")
        self.assertFalse(self._item()["state"]["checked"])

    def test_the_same_key_completes_once(self):
        task = self._create(text="Do x (3)")
        body = {"day": DAY.isoformat(), "idempotency_key": "tap-1"}

        self._post("task-complete", body, task_id=task["id"])
        again = self._post("task-complete", body, task_id=task["id"])
        other = self._post(
            "task-complete", body | {"idempotency_key": "tap-2"}, task_id=task["id"]
        )

        self.assertEqual(again.json()["done_count"], 1)
        self.assertEqual(
            (other.json()["done_count"], other.json()["display"], other.json()["done"]),
            (2, "Do x (3/3)", False),
        )

    def test_a_mark_and_a_note(self):
        task = self._create(text="call bank")

        done = self._post(
            "task-complete",
            {"day": DAY.isoformat(), "at": AT, "mark": "^", "note": "sorted at last"},
            task_id=task["id"],
        )

        self.assertEqual(done.json()["mark"], "^")
        self.assertEqual(Reflection.objects.get(pub_date=DAY).best, "call bank")
        journal = JournalAdded.objects.get()
        self.assertEqual(journal.comment, "- [x] call bank\nsorted at last")
        self.assertEqual(journal.thread, self.daily)

    def test_saved_to_a_trip(self):
        task = self._create(text="call bank")
        trip = start_trip(self.user, title="Away")
        over = start_trip(self.user, title="Over")
        stop_trip(self.user, over.pk)

        stopped = self._post(
            "task-complete",
            {"day": DAY.isoformat(), "story_id": over.pk},
            task_id=task["id"],
        )
        unknown = self._post(
            "task-complete",
            {"day": DAY.isoformat(), "story_id": 999999},
            task_id=task["id"],
        )
        someone = get_user_model().objects.create_user(username="someone")
        theirs = self._post(
            "task-complete",
            {"day": DAY.isoformat(), "story_id": start_trip(someone, title="X").pk},
            task_id=task["id"],
        )
        self.assertEqual(stopped.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(theirs.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(TaskCompleted.objects.exists())

        saved = self._post(
            "task-complete",
            {"day": DAY.isoformat(), "story_id": trip.pk},
            task_id=task["id"],
        )

        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        self.assertTrue(
            trip_links(story=trip, event=JournalAdded.objects.get()).exists()
        )

    def test_the_bodies_the_android_app_sends(self):
        # Its JSON encoder writes defaults, nulls included, and a call
        # without a body is sent with none at all.
        task = self._create(text="call bank", thread="Daily")

        done = self.client.post(
            reverse("task-complete", kwargs={"task_id": task["id"]}),
            {
                "day": DAY.isoformat(),
                "at": "2026-06-25T21:30:00.123+02:00",
                "note": None,
                "story_id": None,
                "idempotency_key": "0b5c1d0e-7a53-4d0b-9d53-2f6d3c1f5a11",
            },
            format="json",
        )
        self.assertEqual(done.status_code, status.HTTP_200_OK, done.content)
        self.assertTrue(done.json()["done"])
        self.assertFalse(JournalAdded.objects.exists())

        reopened = self.client.post(
            reverse("task-reopen", kwargs={"task_id": task["id"]}),
            data=None,
            content_type="application/json",
        )
        self.assertEqual(reopened.status_code, status.HTTP_200_OK, reopened.content)
        self.assertFalse(reopened.json()["done"])

        moved = self._post(
            "task-move",
            {
                "from_date": DAY.isoformat(),
                "to_date": SUNDAY.isoformat(),
                "thread": "Daily",
            },
            task_id=task["id"],
        )
        self.assertEqual(moved.status_code, status.HTTP_200_OK)

        gone = self._post(
            "task-unplan",
            {"date": SUNDAY.isoformat(), "thread": "Daily"},
            task_id=task["id"],
        )
        self.assertEqual(gone.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(gone.content, b"")

    def test_the_day_is_required(self):
        task = self._create(text="call bank")

        response = self._post("task-complete", {"at": AT}, task_id=task["id"])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(TaskCompleted.objects.exists())

    def test_every_write_locks_the_day_before_reading_it(self):
        # The caller's Daily thread is row-locked before a plan or a
        # reflection is read, so two quick taps run one after the other.
        task = self._create(text="Do x (3)")
        friday = (DAY + datetime.timedelta(days=1)).isoformat()
        day = DAY.isoformat()
        writes = [
            ("task-complete", {"day": day}),
            ("task-reopen", {}),
            ("task-plan", {"thread": "Weekly", "date": day}),
            ("task-move", {"from_date": day, "to_date": friday}),
            ("task-unplan", {"thread": "Weekly", "date": day}),
        ]

        for name, body in writes:
            with self.subTest(name):
                with CaptureQueriesContext(connection) as ctx:
                    response = self._post(name, body, task_id=task["id"])
                self.assertEqual(response.status_code, status.HTTP_200_OK)

                sqls = [query["sql"] for query in ctx.captured_queries]
                lock = next(
                    index
                    for index, sql in enumerate(sqls)
                    if 'FROM "tree_thread"' in sql and "FOR UPDATE" in sql
                )
                day_read = next(
                    index
                    for index, sql in enumerate(sqls)
                    if '"tree_plan"' in sql or '"tree_reflection"' in sql
                )
                self.assertLess(lock, day_read)


class ConcurrentWritesTestCase(APITransactionTestCase):
    """Two writes to a day in flight at once (two quick taps on the phone,
    each its own request) both land."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="u", password="x")
        self.daily = Thread.objects.daily(self.user)
        self.bread = plan_task(self.user, "buy bread", DAY)
        self.dog = plan_task(self.user, "walk dog", DAY)

    def _complete_on_another_connection(self, task):
        errors = []

        def run():
            try:
                client = APIClient()
                client.force_authenticate(user=self.user)
                response = client.post(
                    reverse("task-complete", kwargs={"task_id": task.pk}),
                    {"day": DAY.isoformat()},
                    format="json",
                )
                if response.status_code != status.HTTP_200_OK:
                    errors.append(response.content)
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        thread = threading.Thread(target=run)
        thread.start()
        return thread, errors

    def test_concurrent_completions_both_land(self):
        with transaction.atomic():
            lock_day(self.user)
            tasks.complete(self.bread, self.user, day=DAY)
            # The first hasn't committed yet; the second waits for it rather
            # than work from the reflection it would see now.
            thread, errors = self._complete_on_another_connection(self.dog)
            thread.join(timeout=0.5)
            self.assertTrue(thread.is_alive())
        thread.join(timeout=10)

        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(
            [task.done for task in Task.objects.order_by("created")], [True, True]
        )
        reflection = Reflection.objects.get(pub_date=DAY, thread=self.daily)
        self.assertEqual(reflection.good, "buy bread\nwalk dog")


class AccessTestCase(TaskAPITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        User = get_user_model()
        cls.editor = User.objects.create_user(username="editor", password="x")
        cls.stranger = User.objects.create_user(username="stranger", password="x")
        share(cls.user, cls.inbox.board_stream, "editor")

    def test_who_shares_the_board_shares_the_task(self):
        task = self._create(board_id=self.board.pk, item_id=self._item()["id"])
        self.client.force_authenticate(user=self.editor)

        # The same task, on the editor's own plan too.
        theirs = self._create(board_id=self.board.pk, item_id=self._item()["id"])
        self.assertEqual(theirs["id"], task["id"])
        self.assertEqual(
            theirs["plans"], [{"thread": "Daily", "pub_date": DAY.isoformat()}]
        )

        done = self._post("task-complete", {"day": DAY.isoformat()}, task_id=task["id"])

        self.assertEqual(done.status_code, status.HTTP_200_OK)
        self.assertEqual(TaskCompleted.objects.get().created_by, self.editor)
        # Both get it in their own reflection.
        self.assertEqual(
            {
                reflection.thread.user.username: reflection.good
                for reflection in Reflection.objects.filter(pub_date=DAY)
            },
            {"u": "water plants", "editor": "water plants"},
        )
        self.client.force_authenticate(user=self.user)
        self.assertTrue(self._agenda()["daily"]["tasks"][0]["done"])

    def test_a_stranger_finds_no_task(self):
        task = self._create(text="call bank")
        self.client.force_authenticate(user=self.stranger)

        detail = reverse("task-detail", kwargs={"task_id": task["id"]})
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.assertEqual(
            self.client.patch(detail, {"text": "theirs"}, format="json").status_code,
            404,
        )
        for name, body in (
            ("task-plan", {"date": DAY.isoformat()}),
            ("task-unplan", {"date": DAY.isoformat()}),
            (
                "task-move",
                {"from_date": DAY.isoformat(), "to_date": SUNDAY.isoformat()},
            ),
            ("task-complete", {"day": DAY.isoformat()}),
            ("task-reopen", {}),
        ):
            with self.subTest(name=name):
                response = self._post(name, body, task_id=task["id"])
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Task.objects.get().text, "call bank")
        self.assertFalse(TaskCompleted.objects.exists())
        self.assertEqual(self._agenda()["daily"]["tasks"], [])


class OtherWaysToNameATaskTestCase(TaskAPITestCase):
    def test_add_to_plan_by_item_id(self):
        item = self._item()

        response = self.client.post(
            reverse("plan-add-task"),
            {
                "board_id": self.board.pk,
                "item_id": item["id"],
                "timeframe": "this_week",
                "date": DAY.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task = Task.objects.get()
        plan = Plan.objects.get(thread=self.weekly, pub_date=SUNDAY)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "plan_id": plan.pk,
                "plan_date": SUNDAY.isoformat(),
                "task_id": str(task.pk),
            },
        )
        self.assertEqual(self._item()["data"]["taskId"], str(task.pk))

    def test_add_to_plan_of_an_item_that_is_not_there(self):
        response = self.client.post(
            reverse("plan-add-task"),
            {"board_id": self.board.pk, "item_id": "nope", "timeframe": "today"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_board_picker_tells_items_apart(self):
        parent = create_unscheduled_task("parent")
        parent["children"] = [create_unscheduled_task("child")]
        board = make_board(thread=self.inbox, state=[parent])
        child_id = board.state[0]["children"][0]["id"]
        self._create(board_id=board.pk, item_id=child_id)

        items = self.client.get(reverse("android-board-items")).json()["items"]

        self.assertEqual(
            [(i["text"], i["id"], i["board_id"], i["planned"]) for i in items],
            [
                ("parent", board.state[0]["id"], board.pk, False),
                ("child", child_id, board.pk, True),
            ],
        )


class JournalAnchorTestCase(TaskAPITestCase):
    """A journal line that ends with a task's anchor is about that task,
    whatever it says."""

    def _journal(self, comment, thread="Daily", published="2026-06-25T20:00:00Z"):
        response = self.client.post(
            "/journal/",
            {
                "comment": comment,
                "thread": thread,
                "published": published,
                "tags": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return JournalAdded.objects.get(pk=response.json()["id"])

    def test_an_anchored_line_completes_the_task_in_its_authors_words(self):
        task = plan_text(self.user, "call bank", "Daily", DAY, DAY)

        journal = self._journal(
            f"Long day.\r\n- [~] Called them, it took an hour ^t{task.anchor}\r\n- [x] slept well"
        )

        task.refresh_from_db()
        self.assertTrue(task.done)
        reflection = Reflection.objects.get(pub_date=DAY, thread=self.daily)
        self.assertEqual(reflection.better, "Called them, it took an hour")
        self.assertEqual(reflection.good, "slept well")
        line = ReflectionLine.objects.get(task=task)
        self.assertEqual(line.completion, TaskCompleted.objects.get())
        # The anchor did its job; the entry reads without it.
        self.assertEqual(
            journal.comment,
            "Long day.\r\n- [~] Called them, it took an hour\r\n- [x] slept well",
        )

    def test_a_task_planned_for_no_day_is_found_by_its_anchor(self):
        # Nothing on the agenda of that day names it; the anchor does.
        task = plan_text(self.user, "call bank", "Daily", MONTH_END, MONTH_END)

        self._journal(f"- [x] call bank ^t{task.anchor}")

        task.refresh_from_db()
        self.assertTrue(task.done)

    def test_a_counted_task_by_anchor(self):
        task = plan_text(self.user, "Do x (3)", "Daily", DAY, DAY)

        self._journal(f"- [x] first go ^t{task.anchor}")
        self._journal(f"- [x] Do x (3) ^t{task.anchor}")

        task.refresh_from_db()
        self.assertEqual((task.done_count, task.done), (3, True))

    def test_lines_ticked_in_the_cli_journal_template(self):
        # As `tc journal` sends them: the plan lines ticked in the editor,
        # as the template showed them, before what was written.
        bank = plan_text(self.user, "call bank", "Daily", DAY, DAY)
        counted = plan_text(self.user, "Do x (3)", "Daily", DAY, DAY)
        self._post("task-complete", {"day": DAY.isoformat()}, task_id=str(counted.pk))

        journal = self._journal(
            f"- [^] call bank ^t{bank.anchor}\r\n"
            f"- [x] Do x (2/3) ^t{counted.anchor}\r\n"
            "A good day."
        )

        bank.refresh_from_db()
        counted.refresh_from_db()
        self.assertTrue(bank.done)
        self.assertEqual((counted.done_count, counted.done), (2, False))
        reflection = Reflection.objects.get(pub_date=DAY, thread=self.daily)
        self.assertEqual(reflection.best, "call bank")
        self.assertEqual(reflection.good, "Do x (1)\nDo x (2)")
        self.assertEqual(
            journal.comment, "- [^] call bank\r\n- [x] Do x (2/3)\r\nA good day."
        )

    def test_a_weeks_reflection_repeating_a_days_does_not_complete_twice(self):
        task = plan_text(self.user, "call bank", "Daily", DAY, DAY)
        self._journal(f"- [x] call bank ^t{task.anchor}")

        self._journal(
            f"- [x] call bank ^t{task.anchor}",
            thread="Weekly",
            published="2026-06-28T23:59:59Z",
        )

        task.refresh_from_db()
        self.assertEqual(task.done_count, 1)
        self.assertEqual(TaskCompleted.objects.count(), 1)
        weekly = Reflection.objects.get(pub_date=SUNDAY, thread=self.weekly)
        self.assertEqual(weekly.good, "call bank")
        self.assertEqual(weekly.lines.get().task, task)

    def _dump(self, thread="Daily", day=DAY, **params):
        response = self.client.get(
            "/api/events/daily/",
            {"date": day.isoformat(), "thread": thread, **params},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()

    def test_daily_events_give_the_anchors_when_asked(self):
        task = plan_text(self.user, "call bank", "Daily", DAY, DAY)
        self._journal(f"- [x] Called them ^t{task.anchor}\r\n- [x] slept well")

        plain = self._dump()
        self.assertEqual(plain["plan"]["focus"], "call bank")
        self.assertEqual(plain["reflection"]["good"], "Called them\nslept well")

        anchored = self._dump(anchors="1")
        self.assertEqual(anchored["plan"]["focus"], f"call bank ^t{task.anchor}")
        self.assertEqual(
            anchored["reflection"]["good"], f"Called them ^t{task.anchor}\nslept well"
        )
        self.assertEqual(anchored["reflection"]["better"], "")

    def test_a_line_reworded_in_tc_reflect_stays_the_tasks(self):
        # As `tc reflect` sends them: the lines of the days' reflections
        # ticked in the editor, anchors and all, to the week's journal; and
        # those of the weeks' to the month's.
        make_thread(self.user, "big-picture")
        task = plan_text(self.user, "call bank", "Daily", DAY, DAY)
        self._journal(f"- [x] call bank ^t{task.anchor}")
        day_line = self._dump(anchors="1")["reflection"]["good"]

        self._journal(
            f"- [^] {day_line.replace('call bank', 'Sorted the loan at last')}",
            thread="Weekly",
            published="2026-06-28T23:59:59Z",
        )

        week_line = self._dump("Weekly", SUNDAY, anchors="1")["reflection"]["best"]
        self.assertEqual(week_line, f"Sorted the loan at last ^t{task.anchor}")

        self._journal(
            f"- [x] {week_line.replace('at last', 'in June')}",
            thread="big-picture",
            published="2026-06-30T23:59:59Z",
        )

        monthly = Reflection.objects.get(
            pub_date=MONTH_END, thread__name="big-picture", thread__user=self.user
        )
        self.assertEqual(monthly.good, "Sorted the loan in June")
        self.assertEqual(monthly.lines.get().task, task)
        self.assertEqual(TaskCompleted.objects.count(), 1)

    def test_an_anchor_of_nobodys_task_is_just_text(self):
        other = get_user_model().objects.create_user(username="other", password="x")
        theirs = plan_text(other, "their task", "Daily", DAY, DAY)

        journal = self._journal(f"- [x] nice try ^t{theirs.anchor}")

        theirs.refresh_from_db()
        self.assertFalse(theirs.done)
        self.assertEqual(
            Reflection.objects.get(pub_date=DAY, thread=self.daily).good, "nice try"
        )
        self.assertEqual(journal.comment, "- [x] nice try")
