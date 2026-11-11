"""Sample data for a new development database (see
docker/development/devenv.py, which gives every worktree a database of its
own)."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ...board_operations import create_unscheduled_task
from ...models import (
    Board,
    Breakthrough,
    Event,
    Habit,
    HabitKeyword,
    JournalAdded,
    Observation,
    ObservationType,
    ProjectedOutcome,
    Thread,
)
from ...services import streams
from ...services.boards import items
from ...services.journalling import process_journal_entry
from ...services.observations.event_creation import create_observation_change_events
from ...services.tasks import agenda, documents
from ...services.tasks import operations as tasks
from ...services.today import plan_text
from ...services.trips.operations import add_trip_note, start_trip, stop_trip

SHARED_WITH = "alice"

HABITS = (
    ("Exercise", "exercise"),
    ("Reading", "reading"),
    ("Meditation", "meditation"),
)

# (days ago, entry): hashtags track the habits above, [x] and [~] lines go
# into that day's reflection.
JOURNAL = (
    (6, "Slow start, the release went out after lunch. #exercise 30 min bike"),
    (5, "Rainy all day, stayed in. !exercise #reading two chapters"),
    (
        4,
        "Finally sat down with the paperwork.\n"
        "[x] Filed the tax return\n"
        "[~] Skipped lunch again\n"
        "#meditation 10 min before bed",
    ),
    (3, "Ran along the river in the morning. #exercise 5k run #reading"),
    (1, "Long day at work, early night. #meditation"),
    (0, "Walked to work. #exercise walk #reading on the tram"),
)


def _item(text, checked=False, children=()):
    item = create_unscheduled_task(text)
    item["children"] = list(children)
    if checked:
        items.set_checked(item, True)
    return item


def _at(day, hour):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))


class Seed:
    def __init__(self, user, other, today):
        self.user = user
        self.other = other
        self.today = today
        self.daily = Thread.objects.daily(user)

    def run(self):
        self.boards()
        self.plans()
        self.reflection()
        self.habits_and_journal()
        self.observation()
        self.breakthrough()
        self.trip()

    def boards(self):
        states = {
            Thread.DAILY: [
                _item("Reply to the landlord"),
                _item("Fix the bike brakes"),
                _item(
                    "Plan the weekend away",
                    children=[_item("Book the train"), _item("Find a place to stay")],
                ),
                _item("Water the plants", checked=True),
            ],
            Thread.WEEKLY: [
                _item("Write the quarterly review"),
                _item("Clean up the garage"),
                _item("Call grandma"),
            ],
            Thread.BIG_PICTURE: [
                _item("Learn Spanish"),
                _item("Run a half marathon"),
            ],
        }
        for name, state in states.items():
            board = Board.objects.get(thread__user=self.user, thread__name=name)
            board.state = state
            board.save()

        home = Thread.objects.create(user=self.user, name="Home renovation")
        Board.objects.create(
            thread=home,
            state=[
                _item("Pick the bathroom tiles"),
                _item("Get a quote from the plumber"),
            ],
        )
        streams.share(self.user, home.board_stream, self.other.username)

    def plans(self):
        def plan(text, thread_name):
            pub_date = agenda.period_end(thread_name, self.today)
            return plan_text(
                self.user, text, thread_name, pub_date, self.today, any_board=True
            )

        done = plan("Reply to the landlord", Thread.DAILY)
        plan("Fix the bike brakes", Thread.DAILY)
        plan("Buy groceries", Thread.DAILY)
        tasks.complete(done, self.user, day=self.today)

        plan("Write the quarterly review", Thread.WEEKLY)
        plan("Run a half marathon", Thread.BIG_PICTURE)

    def reflection(self):
        yesterday = self.today - datetime.timedelta(days=1)
        reflection = documents.reflection_for(self.daily, yesterday, create=True)
        documents.write(
            reflection,
            {
                "good": "Shipped the release\nLong walk after work",
                "better": "Went to bed too late",
                "best": "Called grandma",
            },
        )

    def habits_and_journal(self):
        for name, keyword in HABITS:
            habit = Habit.objects.create(user=self.user, name=name, slug=keyword)
            HabitKeyword.objects.create(user=self.user, habit=habit, keyword=keyword)

        for days_ago, comment in JOURNAL:
            day = self.today - datetime.timedelta(days=days_ago)
            published = timezone.now() if days_ago == 0 else _at(day, 21)
            entry = JournalAdded.objects.create(
                thread=self.daily,
                comment=comment,
                published=published,
                created_by=self.user,
            )
            process_journal_entry(entry, user=self.user)

    def observation(self):
        kind, _ = ObservationType.objects.get_or_create(
            slug="observation", defaults={"name": "Observation"}
        )
        previous = Observation()
        observation = Observation.objects.create(
            user=self.user,
            thread=self.daily,
            type=kind,
            pub_date=self.today - datetime.timedelta(days=2),
            situation="Said yes to another side project in the meeting.",
            interpretation="Felt flattered, then overwhelmed an hour later.",
            approach="Ask for a day to think before taking anything on.",
        )
        for event in create_observation_change_events(observation, previous=previous):
            event.created_by = self.user
            event.save()
        streams.share(self.user, observation.event_stream, self.other.username)

    def breakthrough(self):
        year = self.today.year
        breakthrough = Breakthrough.objects.create(
            user=self.user,
            slug=str(year),
            theme="Fewer things, done well",
            areas_of_concern="Sleep\nToo many side projects",
        )
        ProjectedOutcome.objects.create(
            breakthrough=breakthrough,
            name="Run a half marathon",
            description="Train three times a week, run the city half in autumn.",
            success_criteria="Finish under 2:10",
            resolved_by=datetime.date(year, 12, 31),
            confidence_level=Decimal("60"),
        )

    def trip(self):
        started = _at(self.today - datetime.timedelta(days=2), 9)
        story = start_trip(self.user, title="Day in the mountains", started=started)
        add_trip_note(
            self.user,
            story.pk,
            "Coffee at the trailhead #poi lat=49.2992 lng=19.9496",
            published=started + datetime.timedelta(hours=1),
        )
        add_trip_note(
            self.user,
            story.pk,
            "Made it to the top, windy but clear. #exercise 14 km hike",
            published=started + datetime.timedelta(hours=5),
        )
        stop_trip(self.user, story.pk, stopped=started + datetime.timedelta(hours=9))


class Command(BaseCommand):
    help = (
        "Fill an account with sample data: boards, plans, a reflection,"
        " habits, journal entries, an observation, a breakthrough and a trip;"
        f" a board and the observation are shared with {SHARED_WITH!r}."
        " Creates the accounts that are missing, with --password."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "username", nargs="?", default="django", help="[default: django]"
        )
        parser.add_argument(
            "--password",
            default="django",
            help="Of the accounts this creates [default: django]",
        )
        parser.add_argument(
            "--new-database-only",
            action="store_true",
            help="Do nothing when the database has any events: a copy of real"
            " data, or one seeded already",
        )

    def handle(self, *args, **options):
        if options["new_database_only"] and Event.objects.exists():
            self.stdout.write("The database has events, not seeding it.")
            return

        with transaction.atomic():
            user = self._account(options["username"], options["password"], True)
            if Event.objects.filter(thread__user=user).exists():
                raise CommandError(
                    f"{user.username} has events already; seed a new account."
                )
            other = self._account(SHARED_WITH, options["password"], False)
            Seed(user, other, timezone.localdate()).run()

        self.stdout.write(f"Seeded {user.username}, sharing with {other.username}.")

    def _account(self, username, password, superuser):
        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if user is not None:
            return user
        create = (
            User.objects.create_superuser if superuser else User.objects.create_user
        )
        return create(username=username, password=password)
