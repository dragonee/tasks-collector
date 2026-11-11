import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from ..models import Board, HabitTracked, Observation, Plan, Story, Task, Thread
from ..services.tasks import documents

User = get_user_model()


def seed(*args):
    out = StringIO()
    call_command("seed_dev", *args, stdout=out)
    return out.getvalue()


class SeedDevTestCase(TestCase):
    def test_creates_both_accounts(self):
        seed()

        django = User.objects.get(username="django")
        alice = User.objects.get(username="alice")
        self.assertTrue(django.is_superuser)
        self.assertTrue(django.check_password("django"))
        self.assertFalse(alice.is_superuser)
        self.assertTrue(alice.check_password("django"))

    def test_plans_today_with_one_task_done(self):
        seed()
        django = User.objects.get(username="django")
        today = timezone.localdate()

        plan = Plan.objects.get(thread=Thread.objects.daily(django), pub_date=today)
        self.assertEqual(
            plan.focus, "Reply to the landlord\nFix the bike brakes\nBuy groceries"
        )
        done = Task.objects.filter(user=django, completed_at__isnull=False)
        self.assertEqual([t.text for t in done], ["Reply to the landlord"])

    def test_journal_tracks_habits_and_fills_reflections(self):
        seed()
        django = User.objects.get(username="django")

        exercise = HabitTracked.objects.filter(
            habit__user=django, habit__slug="exercise"
        )
        self.assertEqual(exercise.filter(occured=True).count(), 4)
        self.assertEqual(exercise.filter(occured=False).count(), 1)

        day = timezone.localdate() - datetime.timedelta(days=4)
        reflection = documents.reflection_for(Thread.objects.daily(django), day)
        self.assertEqual(reflection.good, "Filed the tax return")

    def test_shares_a_board_and_the_observation_with_alice(self):
        seed()
        alice = User.objects.get(username="alice")

        shared = Board.objects.editable_by(alice).exclude(thread__user=alice)
        self.assertEqual([b.thread.name for b in shared], ["Home renovation"])
        self.assertEqual(Observation.objects.visible_to(alice).count(), 1)

    def test_records_a_finished_trip(self):
        seed()

        story = Story.objects.get(user__username="django")
        self.assertIsNotNone(story.stopped)

    def test_refuses_an_account_with_events(self):
        seed()

        with self.assertRaises(CommandError):
            seed()

    def test_new_database_only_leaves_a_database_with_events_alone(self):
        seed()

        out = seed("bob", "--new-database-only")

        self.assertIn("not seeding", out)
        self.assertFalse(User.objects.filter(username="bob").exists())
