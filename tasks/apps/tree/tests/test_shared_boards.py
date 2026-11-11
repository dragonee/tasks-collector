"""Sharing a board lets another user work on it: read it, change it, tick its
tasks from the Android app or the journal, append to it and commit it. The
owner's other boards and everything else stay private."""

import datetime

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from ..board_operations import board_thread_for, create_unscheduled_task
from ..forms import DefaultBoardForm
from ..models import (
    Board,
    BoardCommitted,
    EventStreamAccess,
    Plan,
    Profile,
    Reflection,
    Task,
    TaskCompleted,
    Thread,
)
from ..services.streams import SharingError, revoke, share, shared_with
from ..services.tasks import agenda
from .factories import (
    complete,
    make_board,
    make_profile,
    make_thread,
    make_token,
    plan_task,
)

User = get_user_model()

TODAY = datetime.date(2026, 11, 11)


def _item(text, transition=None):
    item = create_unscheduled_task(text)
    if transition:
        item["data"]["meaningfulMarkers"]["transition"] = transition
    return item


def _texts(board):
    return [node["text"] for node in board.state]


class SharedBoardTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        cls.carol = User.objects.create_user(username="carol", password="x")

        cls.together = make_thread(cls.alice, "Together")
        cls.board = make_board(cls.together, state=[_item("buy bread")])
        cls.alices_daily_board = make_board(
            Thread.objects.daily(cls.alice), state=[_item("alice's own task")]
        )

        share(cls.alice, cls.together.board_stream, "bob")

    def setUp(self):
        self.client.force_authenticate(user=self.bob)

    def _board(self):
        return Board.objects.get(pk=self.board.pk)


class ShareBoardTestCase(SharedBoardTestCase):
    def test_sharing_a_board_makes_an_editor(self):
        self.assertEqual(list(shared_with(self.together.board_stream)), [self.bob])
        self.assertEqual(
            EventStreamAccess.objects.get(
                stream=self.together.board_stream, user=self.bob
            ).role,
            EventStreamAccess.Role.EDITOR,
        )

    def test_an_editor_cannot_pass_it_on(self):
        with self.assertRaises(SharingError):
            share(self.bob, self.together.board_stream, "carol")

    def test_a_builtin_board_cannot_be_shared_through_the_endpoint(self):
        self.client.force_login(self.alice)
        daily = Thread.objects.daily(self.alice)

        response = self.client.post(
            f"/streams/{daily.board_stream_id}/sharing/",
            {"action": "share", "username": "bob"},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_owner_shares_from_the_settings_page(self):
        self.client.force_login(self.alice)

        page = self.client.get(reverse("settings-boards"))

        self.assertContains(page, 'id="shared-boards"')
        self.assertContains(page, "Together")
        self.assertContains(page, "change this board")
        self.assertContains(page, 'class="settings-shared-board"', count=1)

        response = self.client.post(
            f"/streams/{self.together.board_stream_id}/sharing/",
            {
                "action": "share",
                "username": "carol",
                "next": reverse("settings-boards"),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertContains(response, "carol")
        self.assertEqual(
            list(shared_with(self.together.board_stream)), [self.bob, self.carol]
        )

    def test_a_user_without_custom_boards_gets_no_sharing_section(self):
        self.client.force_login(self.carol)

        page = self.client.get(reverse("settings-boards"))

        self.assertNotContains(page, 'id="shared-boards"')


class EditorTestCase(SharedBoardTestCase):
    def test_the_editor_reads_and_changes_the_board(self):
        listed = self.client.get("/boards/", {"thread": self.together.pk})

        self.assertEqual([b["id"] for b in listed.json()["results"]], [self.board.pk])
        self.assertEqual(listed.json()["results"][0]["thread"]["shared_by"], "alice")

        state = self._board().state + [_item("milk")]
        response = self.client.put(
            f"/boards/{self.board.pk}/",
            {"state": state, "focus": "weekend"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_texts(self._board()), ["buy bread", "milk"])

    def test_the_editor_sees_none_of_the_owners_other_boards(self):
        listed = self.client.get("/boards/")

        thread_ids = {b["thread"]["id"] for b in listed.json()["results"]}
        self.assertIn(self.together.pk, thread_ids)
        self.assertNotIn(self.alices_daily_board.thread_id, thread_ids)
        response = self.client.get(f"/boards/{self.alices_daily_board.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_threads_list_the_shared_board_after_the_users_own(self):
        threads = self.client.get("/threads/").json()["results"]
        listed = [(t["name"], t["shared_by"]) for t in threads]

        # Own threads by name, in the database's collation (it differs between
        # dev and CI), then the shared board.
        self.assertCountEqual(
            listed[:3], [("Daily", None), ("Weekly", None), ("big-picture", None)]
        )
        self.assertEqual(listed[3:], [("Together", "alice")])

    def test_the_editor_commits_and_marked_items_go_to_their_own_threads(self):
        make_board(
            self.together,
            state=[_item("stays"), _item("for my day", transition="Daily")],
        )

        response = self.client.post(f"/boards/{self.board.pk}/commit/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_texts(self._board()), ["stays"])
        bobs_daily = Board.objects.get(thread=Thread.objects.daily(self.bob))
        self.assertEqual(_texts(bobs_daily), ["for my day"])
        self.assertEqual(
            _texts(Board.objects.get(pk=self.alices_daily_board.pk)),
            ["alice's own task"],
        )
        committed = BoardCommitted.objects.get(thread=self.together)
        self.assertEqual(committed.created_by, self.bob)
        self.assertEqual(committed.event_stream_id, self.together.board_stream_id)

    def test_the_editor_appends_by_name_and_to_the_default_board(self):
        make_profile(self.bob, default_board_thread=self.together)

        by_default = self.client.post(
            "/boards/append/", {"text": "milk"}, format="json"
        )
        by_name = self.client.post(
            "/boards/append/",
            {"text": "eggs", "thread-name": "Together"},
            format="json",
        )

        self.assertEqual(by_default.status_code, status.HTTP_200_OK)
        self.assertEqual(by_name.status_code, status.HTTP_200_OK)
        self.assertEqual(by_name.json()["thread"]["shared_by"], "alice")
        self.assertEqual(_texts(self._board()), ["buy bread", "milk", "eggs"])

    def test_android_works_on_the_shared_default_board(self):
        make_profile(self.bob, default_board_thread=self.together)
        token = make_token(self.bob)
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        items = self.client.get(reverse("android-board-items"))
        (bread,) = items.json()["items"]
        added = self.client.post(
            reverse("task-create"),
            {"text": "call the plumber", "date": TODAY.isoformat()},
            format="json",
        )

        planned = self.client.post(
            reverse("task-create"),
            {
                "board_id": bread["board_id"],
                "item_id": bread["id"],
                "date": TODAY.isoformat(),
            },
            format="json",
        )

        self.assertEqual(bread["text"], "buy bread")
        self.assertEqual(added.status_code, status.HTTP_201_CREATED)
        self.assertEqual(planned.status_code, status.HTTP_201_CREATED)
        # What he typed in is a task, not an item of the board.
        self.assertEqual(_texts(self._board()), ["buy bread"])
        plan = Plan.objects.get(pub_date=TODAY)
        self.assertEqual(plan.thread, Thread.objects.daily(self.bob))
        self.assertEqual(plan.focus, "call the plumber\nbuy bread")

        # Both tasks live in the stream of the shared board: whoever has the
        # board has them.
        typed, from_board = Task.objects.order_by("created")
        self.assertEqual(self._board().state[0]["data"]["taskId"], str(from_board.pk))
        for task in (typed, from_board):
            self.assertEqual(task.event_stream_id, self.together.board_stream_id)
        self.assertEqual(set(Task.objects.visible_to(self.alice)), {typed, from_board})
        self.assertEqual(set(Task.objects.editable_by(self.bob)), {typed, from_board})

    def test_a_shared_item_planned_by_both_is_one_task(self):
        make_profile(self.alice, default_board_thread=self.together)
        make_profile(self.bob, default_board_thread=self.together)

        plan_task(self.bob, "buy bread", TODAY)
        plan_task(self.alice, "buy bread", TODAY)

        task = Task.objects.get()
        self.assertEqual(task.user, self.bob)
        self.assertEqual(
            {line.plan.thread.user for line in task.plan_lines.all()},
            {self.alice, self.bob},
        )

        # Either of them completes it; both get it in their reflection, and
        # the board item is ticked.
        complete(task, self.alice, TODAY)

        for user in (self.alice, self.bob):
            (shown,) = agenda.plan_tasks(user, TODAY, Thread.DAILY)
            self.assertTrue(shown.done)
            reflection = Reflection.objects.get(
                pub_date=TODAY, thread=Thread.objects.daily(user)
            )
            self.assertEqual(reflection.good, "buy bread")
        self.assertTrue(self._board().state[0]["state"]["checked"])
        completion = TaskCompleted.objects.get()
        self.assertEqual(completion.created_by, self.alice)
        self.assertEqual(completion.thread, self.together)

    def test_a_stranger_cannot_see_the_tasks_of_the_board(self):
        make_profile(self.bob, default_board_thread=self.together)
        plan_task(self.bob, "buy bread", TODAY)
        carol = User.objects.create_user(username="carol2", password="x")

        self.assertFalse(Task.objects.visible_to(carol).exists())

    def test_the_profile_offers_the_shared_board(self):
        form = DefaultBoardForm(
            user=self.bob, instance=Profile.objects.get(user=self.bob)
        )

        choices = [label for _, label in form.fields["default_board_thread"].choices]

        self.assertIn("Together (shared by alice)", choices)
        self.client.force_login(self.bob)
        self.client.post(
            reverse("settings-boards"), {"default_board_thread": self.together.pk}
        )
        self.assertEqual(board_thread_for(self.bob), self.together)


class NoAccessTestCase(SharedBoardTestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.carol)

    def test_a_stranger_gets_nothing(self):
        listed = self.client.get("/boards/", {"thread": self.together.pk})
        put = self.client.put(f"/boards/{self.board.pk}/", {"state": []}, format="json")
        commit = self.client.post(f"/boards/{self.board.pk}/commit/")
        append = self.client.post(
            "/boards/append/",
            {"text": "x", "thread-name": "Together"},
            format="json",
        )

        self.assertEqual(listed.json()["results"], [])
        self.assertEqual(put.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(commit.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(append.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(_texts(self._board()), ["buy bread"])
        names = [t["name"] for t in self.client.get("/threads/").json()["results"]]
        self.assertNotIn("Together", names)

    def test_the_profile_refuses_a_board_not_shared(self):
        form = DefaultBoardForm(
            {"default_board_thread": self.together.pk},
            user=self.carol,
            instance=Profile.objects.get(user=self.carol),
        )

        self.assertIn("default_board_thread", form.errors)

    def test_a_default_board_without_access_is_ignored(self):
        # A profile pointing at someone else's board from before threads had
        # owners, or a board no longer shared.
        make_profile(self.carol, default_board_thread=self.together)

        self.assertEqual(board_thread_for(self.carol), Thread.objects.daily(self.carol))

    def test_revoking_ends_access_and_the_default_board(self):
        make_profile(self.bob, default_board_thread=self.together)

        revoke(self.alice, self.together.board_stream, "bob")

        self.assertIsNone(Profile.objects.get(user=self.bob).default_board_thread)
        self.assertEqual(board_thread_for(self.bob), Thread.objects.daily(self.bob))
        self.client.force_authenticate(user=self.bob)
        listed = self.client.get("/boards/", {"thread": self.together.pk})
        self.assertEqual(listed.json()["results"], [])


class SummariesTestCase(SharedBoardTestCase):
    def _commit(self, user, board, state):
        make_board(board.thread, state=state)
        self.client.force_authenticate(user=user)
        response = self.client.post(f"/boards/{board.pk}/commit/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return BoardCommitted.objects.filter(thread=board.thread).latest("published")

    def test_the_editor_sees_every_commit_of_the_shared_board(self):
        by_alice = self._commit(self.alice, self.board, [_item("alice's week")])
        by_bob = self._commit(self.bob, self.board, [_item("bob's week")])
        self.client.force_login(self.bob)

        page = self.client.get(reverse("summaries"))

        self.assertContains(page, f'id="summary-{by_alice.pk}"')
        self.assertContains(page, f'id="summary-{by_bob.pk}"')
        self.assertContains(page, "Together, shared by alice")
        self.assertContains(page, "committed by alice")
        single = self.client.get(reverse("board-summary", args=[by_alice.pk]))
        self.assertContains(single, f'id="summary-{by_alice.pk}"')
        self.assertContains(single, "Together, shared by alice")

    def test_the_owner_sees_who_committed(self):
        by_bob = self._commit(self.bob, self.board, [_item("bob's week")])
        self.client.force_login(self.alice)

        page = self.client.get(reverse("summaries"))

        self.assertContains(page, f'id="summary-{by_bob.pk}"')
        self.assertContains(page, "committed by bob")
        self.assertNotContains(page, "shared by")

    def test_a_stranger_sees_no_summary(self):
        by_alice = self._commit(self.alice, self.board, [_item("alice's week")])
        self.client.force_login(self.carol)

        page = self.client.get(reverse("summaries"))
        single = self.client.get(reverse("board-summary", args=[by_alice.pk]))

        self.assertNotContains(page, f'id="summary-{by_alice.pk}"')
        self.assertEqual(single.status_code, status.HTTP_404_NOT_FOUND)


class MoveIntoSharedBoardTestCase(SharedBoardTestCase):
    def test_the_editor_moves_items_from_their_board_into_the_shared_one(self):
        daily = make_board(
            Thread.objects.daily(self.bob),
            state=[_item("mine"), _item("ours", transition="Together")],
        )

        response = self.client.post(f"/boards/{daily.pk}/commit/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_texts(self._board()), ["buy bread", "ours"])
        self.assertEqual(_texts(Board.objects.get(pk=daily.pk)), ["mine"])

    def test_their_own_board_of_the_same_name_wins(self):
        bobs_together = make_board(make_thread(self.bob, "Together"))
        daily = make_board(
            Thread.objects.daily(self.bob),
            state=[_item("ours", transition="Together")],
        )

        self.client.post(f"/boards/{daily.pk}/commit/")

        self.assertEqual(_texts(Board.objects.get(pk=bobs_together.pk)), ["ours"])
        self.assertEqual(_texts(self._board()), ["buy bread"])

    def test_a_stranger_cannot_move_items_into_it(self):
        daily = make_board(
            Thread.objects.daily(self.carol),
            state=[_item("theirs", transition="Together")],
        )
        self.client.force_authenticate(user=self.carol)

        response = self.client.post(f"/boards/{daily.pk}/commit/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(_texts(self._board()), ["buy bread"])


class DeletingUsersTestCase(SharedBoardTestCase):
    def setUp(self):
        super().setUp()
        make_board(self.together, state=[_item("bob's week")])
        response = self.client.post(f"/boards/{self.board.pk}/commit/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.commit = BoardCommitted.objects.get(thread=self.together)

    def test_deleting_an_editor_keeps_their_commits_on_the_board(self):
        self.bob.delete()

        self.commit.refresh_from_db()
        self.assertIsNone(self.commit.created_by)
        self.assertEqual(self.commit.event_stream_id, self.together.board_stream_id)
        self.assertEqual(list(shared_with(self.together.board_stream)), [])
        self.client.force_login(self.alice)
        page = self.client.get(reverse("summaries"))
        self.assertContains(page, "committed by a deleted user")

    def test_saving_a_commit_whose_writer_was_deleted_keeps_it_unknown(self):
        self.bob.delete()
        self.commit.refresh_from_db()

        self.commit.focus = "renamed"
        self.commit.save()

        self.commit.refresh_from_db()
        self.assertIsNone(self.commit.created_by)

    def test_deleting_the_owner_takes_the_board_and_its_commits(self):
        make_profile(self.bob, default_board_thread=self.together)

        self.alice.delete()

        self.assertFalse(Board.objects.filter(pk=self.board.pk).exists())
        self.assertFalse(BoardCommitted.objects.filter(pk=self.commit.pk).exists())
        self.assertIsNone(Profile.objects.get(user=self.bob).default_board_thread)
        self.assertEqual(board_thread_for(self.bob), Thread.objects.daily(self.bob))


class BoardPageSharingTestCase(SharedBoardTestCase):
    """The board page shares the board shown through
    ``api/streams/<id>/sharing/``, offered where ``shareable`` is true."""

    def url(self, stream=None):
        stream = stream or self.together.board_stream
        return reverse("stream-sharing-api", args=[stream.pk])

    def setUp(self):
        self.client.force_authenticate(user=self.alice)

    def test_threads_say_which_boards_the_user_can_share(self):
        threads = {t["name"]: t for t in self.client.get("/threads/").json()["results"]}

        self.assertTrue(threads["Together"]["shareable"])
        self.assertEqual(
            threads["Together"]["board_stream"], str(self.together.board_stream_id)
        )
        self.assertFalse(threads["Daily"]["shareable"])
        self.client.force_authenticate(user=self.bob)
        threads = {t["name"]: t for t in self.client.get("/threads/").json()["results"]}
        self.assertFalse(threads["Together"]["shareable"])

    def test_the_owner_reads_shares_and_revokes(self):
        read = self.client.get(self.url())
        shared = self.client.post(
            self.url(), {"action": "share", "username": "carol"}, format="json"
        )
        revoked = self.client.post(
            self.url(), {"action": "revoke", "username": "bob"}, format="json"
        )

        self.assertEqual(
            read.json(),
            {
                "stream": str(self.together.board_stream_id),
                "role": "editor",
                "shared_with": ["bob"],
                "error": None,
            },
        )
        self.assertEqual(shared.json()["shared_with"], ["bob", "carol"])
        self.assertEqual(revoked.json()["shared_with"], ["carol"])
        self.assertEqual(list(shared_with(self.together.board_stream)), [self.carol])

    def test_a_share_that_cant_be_done_says_why(self):
        response = self.client.post(
            self.url(), {"action": "share", "username": "nobody"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("no user called", response.json()["error"])
        self.assertEqual(response.json()["shared_with"], ["bob"])

    def test_a_malformed_request_is_refused(self):
        for body in ({"action": "share"}, {"action": "x", "username": "carol"}, [1]):
            with self.subTest(body=body):
                response = self.client.post(self.url(), body, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_the_owner_of_a_shareable_board_gets_it(self):
        daily = Thread.objects.daily(self.alice)
        builtin = self.client.get(self.url(daily.board_stream))
        self.client.force_authenticate(user=self.bob)
        editor = self.client.get(self.url())
        editor_post = self.client.post(
            self.url(), {"action": "share", "username": "carol"}, format="json"
        )

        self.assertEqual(builtin.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(editor.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(editor_post.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(list(shared_with(self.together.board_stream)), [self.bob])


class MoveToOwnBoardTestCase(SharedBoardTestCase):
    def test_items_move_to_any_of_the_users_own_boards(self):
        self.client.force_authenticate(user=self.alice)
        inbox = make_board(make_thread(self.alice, "Inbox"))
        daily = make_board(
            Thread.objects.daily(self.alice),
            state=[_item("stays"), _item("later", transition="Inbox")],
        )

        response = self.client.post(f"/boards/{daily.pk}/commit/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_texts(Board.objects.get(pk=inbox.pk)), ["later"])
        self.assertEqual(_texts(Board.objects.get(pk=daily.pk)), ["stays"])
