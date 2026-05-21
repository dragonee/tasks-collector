from datetime import date as date_cls
from datetime import datetime as datetime_cls
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from ..models import Board, JournalAdded, Plan, Profile, Reflection, Thread

TODAY = date_cls(2026, 5, 21)
TODAY_ISO = TODAY.isoformat()
# Full ISO 8601 timestamp the Android client would send on /complete.
COMPLETE_AT = datetime_cls(2026, 5, 21, 15, 42, 33, tzinfo=dt_timezone.utc)
COMPLETE_AT_ISO = COMPLETE_AT.isoformat()


class AndroidTaskAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="phone", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.daily = Thread.objects.create(name="Daily")
        Profile.objects.create(user=cls.user, default_board_thread=cls.daily)
        cls.board = Board.objects.create(thread=cls.daily, state=[])

    def setUp(self):
        self.board = Board.objects.get(pk=self.board.pk)
        self.board.state = []
        self.board.save()
        Plan.objects.filter(thread=self.daily).delete()
        Reflection.objects.filter(thread=self.daily).delete()

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _add(self, text, date=TODAY_ISO):
        return self.client.post(
            reverse("android-task-add"),
            {"text": text, "date": date},
            format="json",
        )

    def _complete(self, text, done, date=COMPLETE_AT_ISO, **extra):
        payload = {"text": text, "done": done, "date": date}
        payload.update(extra)
        return self.client.post(
            reverse("android-task-complete"),
            payload,
            format="json",
        )

    def _delete(self, text, date=TODAY_ISO):
        return self.client.post(
            reverse("android-task-delete"),
            {"text": text, "date": date},
            format="json",
        )

    def _list(self, date=TODAY_ISO):
        url = reverse("android-task-today")
        if date is None:
            return self.client.get(url)
        return self.client.get(url, {"date": date})

    def test_add_creates_board_node_and_plan_line(self):
        self._auth()
        response = self._add("buy bread")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"ok": True})

        self.board.refresh_from_db()
        self.assertEqual(len(self.board.state), 1)
        self.assertEqual(self.board.state[0]["text"], "buy bread")
        plan = Plan.objects.get(thread=self.daily)
        self.assertEqual(plan.pub_date, TODAY)

    def test_complete_then_uncomplete_round_trip(self):
        self._auth()
        self._add("buy bread")

        response = self._complete("buy bread", True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "buy bread")
        self.assertEqual(reflection.pub_date, TODAY)

        response = self._complete("buy bread", False)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reflection.refresh_from_db()
        self.assertEqual(reflection.good, "")

    def test_delete_removes_plan_line(self):
        self._auth()
        self._add("buy bread")
        response = self._delete("buy bread")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        plan = Plan.objects.get(thread=self.daily)
        self.assertEqual(plan.focus, "")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state, [])

    def test_list_returns_done_flag_and_unchecked_first(self):
        self._auth()
        for line in ("alpha", "bravo"):
            self._add(line)
        self._complete("alpha", True)

        response = self._list()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {"text": "bravo", "done": False},
                    {"text": "alpha", "done": True},
                ]
            },
        )

    def test_date_drives_target_plan(self):
        """A request that names a different date hits that day's Plan,
        regardless of the server's clock."""
        self._auth()
        yesterday = (TODAY - timedelta(days=1)).isoformat()  # 2026-05-20
        self._add("buy bread", date=yesterday)
        self._add("walk dog", date=TODAY_ISO)

        plans = {p.pub_date.isoformat(): p.focus for p in Plan.objects.all()}
        self.assertEqual(plans[yesterday], "buy bread")
        self.assertEqual(plans[TODAY_ISO], "walk dog")

        # Listing yesterday only shows yesterday's task.
        response = self._list(date=yesterday)
        self.assertEqual(
            response.json(),
            {"items": [{"text": "buy bread", "done": False}]},
        )

    def test_missing_token_returns_401(self):
        response = self._list()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_add_missing_text_returns_400(self):
        self._auth()
        response = self.client.post(
            reverse("android-task-add"), {"date": TODAY_ISO}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_complete_missing_done_returns_400(self):
        self._auth()
        response = self.client.post(
            reverse("android-task-complete"),
            {"text": "x", "date": TODAY_ISO},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_missing_date_returns_400(self):
        self._auth()
        response = self.client.post(
            reverse("android-task-add"), {"text": "x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_missing_date_returns_400(self):
        self._auth()
        response = self._list(date=None)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_malformed_date_returns_400(self):
        self._auth()
        response = self._add("x", date="not-a-date")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self._list(date="2026/05/21")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_board_returns_409(self):
        Board.objects.all().delete()
        self._auth()
        response = self._add("x")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_progress_task_advances_via_repeated_complete(self):
        """Three POSTs to /complete on a (3) task should advance it to (3/3)
        and flip the list's done flag."""
        self._auth()
        self._add("Do tasks (3)")

        self._complete("Do tasks (3)", True)
        self.assertEqual(
            self._list().json(),
            {"items": [{"text": "Do tasks (1/3)", "done": False}]},
        )

        self._complete("Do tasks (1/3)", True)
        self.assertEqual(
            self._list().json(),
            {"items": [{"text": "Do tasks (2/3)", "done": False}]},
        )

        self._complete("Do tasks (2/3)", True)
        self.assertEqual(
            self._list().json(),
            {"items": [{"text": "Do tasks (3/3)", "done": True}]},
        )

        # Reflection.good and board state should both reflect completion.
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "Do tasks (3/3)")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["text"], "Do tasks (3/3)")
        self.assertEqual(self.board.state[0]["data"]["state"], "done")

        # Untick resets to pristine.
        self._complete("Do tasks (3/3)", False)
        self.assertEqual(
            self._list().json(),
            {"items": [{"text": "Do tasks (3)", "done": False}]},
        )
        reflection.refresh_from_db()
        self.assertEqual(reflection.good, "")
        self.board.refresh_from_db()
        self.assertEqual(self.board.state[0]["data"]["state"], "open")

    # --- journal-note modal contract -------------------------------------

    def test_complete_with_note_creates_journal_entry(self):
        self._auth()
        self._add("buy bread")

        response = self._complete("buy bread", True, note="bought rye instead")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        entry = JournalAdded.objects.get(thread=self.daily)
        self.assertEqual(entry.comment, "- [x] buy bread\nbought rye instead")
        # Timestamp is taken verbatim from the request, not synthesized.
        self.assertEqual(entry.published, COMPLETE_AT)

    def test_complete_with_empty_note_creates_no_journal_entry(self):
        self._auth()
        self._add("buy bread")

        self._complete("buy bread", True, note="")

        # Empty note from the modal means "just confirm the tick" — no
        # journal entry is recorded.
        self.assertFalse(JournalAdded.objects.exists())

    def test_complete_without_note_creates_no_journal_entry(self):
        self._auth()
        self._add("buy bread")

        self._complete("buy bread", True)  # no note field

        self.assertFalse(JournalAdded.objects.exists())

    def test_uncheck_ignores_note(self):
        self._auth()
        self._add("buy bread")
        self._complete("buy bread", True, note="first")

        # Reset state and clear journal so we can spot a forbidden write.
        JournalAdded.objects.all().delete()

        self._complete("buy bread", False, note="ignored on uncheck")

        self.assertFalse(JournalAdded.objects.exists())

    def test_complete_with_non_string_note_returns_400(self):
        self._auth()
        self._add("buy bread")
        response = self._complete("buy bread", True, note=123)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_complete_with_date_only_returns_400(self):
        """/complete now requires a full ISO 8601 timestamp; date-only is
        rejected so the journal entry can carry a real wall-clock time."""
        self._auth()
        self._add("buy bread")
        response = self._complete("buy bread", True, date=TODAY_ISO)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_complete_with_progress_task_journals_post_tick_text(self):
        self._auth()
        self._add("Do tasks (3)")

        self._complete("Do tasks (3)", True, note="step one done")

        entry = JournalAdded.objects.get(thread=self.daily)
        # Post-tick text in the [x] line, then the user's note.
        self.assertEqual(entry.comment, "- [x] Do tasks (1/3)\nstep one done")

    def test_add_another_advances_past_full(self):
        """End-to-end Add another flow: a /complete on a fully-completed
        progress task bumps it to (N+1/N), keeps the row checked, and
        records a journal entry with the new over-quota text."""
        self._auth()
        self._add("Do tasks (1)")
        # First tick: (1) → (1/1), done.
        self._complete("Do tasks (1)", True, note="first")
        self.assertEqual(
            self._list().json(),
            {"items": [{"text": "Do tasks (1/1)", "done": True}]},
        )
        # "Add another" tick on the already-done task → (2/1), still done.
        self._complete("Do tasks (1/1)", True, note="another one")

        self.assertEqual(
            self._list().json(),
            {"items": [{"text": "Do tasks (2/1)", "done": True}]},
        )
        # Reflection.good renamed in place — single line, new text.
        reflection = Reflection.objects.get(thread=self.daily)
        self.assertEqual(reflection.good, "Do tasks (2/1)")
        # Board row stays checked.
        self.board.refresh_from_db()
        self.assertTrue(self.board.state[0]["state"]["checked"])
        # Two journal entries, one per tick.
        self.assertEqual(
            sorted(JournalAdded.objects.values_list("comment", flat=True)),
            sorted(
                [
                    "- [x] Do tasks (1/1)\nfirst",
                    "- [x] Do tasks (2/1)\nanother one",
                ]
            ),
        )
