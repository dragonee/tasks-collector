"""What sending a journal entry would do, asked without sending it
(api/v1/journal/preview/)."""

import datetime

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework.test import APITestCase

from ..board_operations import create_unscheduled_task
from ..models import HabitTracked, JournalAdded, Reflection, ReflectionLine, Thread
from .factories import make_board, make_habit, make_profile, make_thread, plan_task

WEDNESDAY = datetime.date(2026, 6, 24)
SUNDAY_EVENING = "2026-06-28T23:59:59+00:00"


class JournalPreviewTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.weekly = make_thread(cls.user, Thread.WEEKLY)
        cls.inbox = make_thread(cls.user, "Inbox")
        make_profile(cls.user, default_board_thread=cls.inbox)
        make_board(cls.inbox, state=[create_unscheduled_task("water plants")])
        make_habit(cls.user, "Breakthrough", keywords=["breakthrough"])
        cls.task = plan_task(cls.user, "Write the review", WEDNESDAY, Thread.WEEKLY)

    def setUp(self):
        self.client.force_authenticate(self.user)

    def _preview(self, comment, thread=Thread.WEEKLY):
        return self.client.post(
            reverse("journal-preview"),
            {
                "comment": comment,
                "thread": thread,
                "published": SUNDAY_EVENING,
                "tags": [],
            },
            format="json",
        )

    def test_it_says_what_the_entry_would_add(self):
        response = self._preview(
            "Makimo\n\n"
            "- [x] Called the client\n"
            "- [~] Slept too little\n"
            f"- [^] Wrote it at last ^t{self.task.anchor}\n"
            "- [x] water plants\n"
            "\n"
            "Today #breakthrough the first talk"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["thread"], "Weekly")
        self.assertNotIn("^t", data["comment"])
        self.assertEqual(data["reflection"]["date"], "2026-06-28")
        self.assertEqual(
            data["reflection"]["good"],
            [
                {"text": "Called the client", "anchor": None},
                {"text": "water plants", "anchor": None},
            ],
        )
        self.assertEqual(
            data["reflection"]["better"], [{"text": "Slept too little", "anchor": None}]
        )
        self.assertEqual(
            [line["anchor"] for line in data["reflection"]["best"]], [self.task.anchor]
        )
        self.assertEqual(
            data["tasks_completed"],
            [{"text": "Write the review", "anchor": self.task.anchor}],
        )
        self.assertEqual(
            [(habit["habit"], habit["occured"]) for habit in data["habits"]],
            [("Breakthrough", True)],
        )
        self.assertEqual(data["unscheduled_tasks_ticked"], ["water plants"])

    def test_it_changes_nothing(self):
        self._preview(
            f"- [x] Called the client\n- [^] Done ^t{self.task.anchor}\n#breakthrough"
        )

        self.task.refresh_from_db()
        self.assertFalse(self.task.done)
        self.assertFalse(JournalAdded.objects.exists())
        self.assertFalse(HabitTracked.objects.exists())
        self.assertFalse(ReflectionLine.objects.exists())
        self.assertFalse(Reflection.objects.filter(thread=self.weekly).exists())

    def test_an_entry_it_would_refuse_is_refused(self):
        response = self._preview("- [x] something", thread="No such thread")

        self.assertEqual(response.status_code, 400)
