"""Every route of the app keeps one user's data from another.

Alice has one of everything, every text of it carrying SECRET. Bob calls
every route with every method, pointing at Alice's objects wherever a route
takes an id. Nothing he gets back may show Alice's data, nothing may fail
with a server error, and afterwards Alice's data must be exactly as before.

A new route is covered automatically. A route whose URL takes a parameter
this test doesn't know makes it fail: add the parameter to ``url_kwargs``.
"""

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone

from rest_framework.test import APITestCase

from ..models import (
    Board,
    BoardCommitted,
    Breakthrough,
    Event,
    EventStreamAccess,
    EventStreamEntry,
    Habit,
    HabitKeyword,
    HabitTracked,
    InsightRefined,
    JournalAdded,
    JournalTag,
    Observation,
    ObservationType,
    ObservationUpdated,
    PhotoAdded,
    Plan,
    Profile,
    ProjectedOutcome,
    Reflection,
    SharedStory,
    Story,
    Thread,
)
from ..services.observations.closing import close_observation
from ..services.trips import add_trip_note, share_trip, start_trip
from .factories import make_habit, make_thread

SECRET = "ALICE-SECRET"

# Reachable without logging in, by design: a share link is the capability.
PUBLIC_ROUTES = {"trip-shared-detail"}

METHODS = ("get", "post", "put", "patch", "delete")


def _routes(patterns=None, prefix=""):
    """(route, name, pattern) for every route served by the tree app."""
    for pattern in patterns if patterns is not None else get_resolver().url_patterns:
        if isinstance(pattern, URLResolver):
            yield from _routes(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            callback = pattern.callback
            view = getattr(callback, "cls", None) or getattr(
                callback, "view_class", callback
            )
            if getattr(view, "__module__", "").startswith("tasks.apps.tree."):
                yield prefix + str(pattern.pattern), pattern.name, pattern


class RouteIsolationTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        alice = cls.alice
        now = timezone.make_aware(datetime.datetime(2026, 11, 10, 12))
        cls.day = now.date()
        daily = Thread.objects.daily(alice)
        secret_thread = make_thread(alice, f"{SECRET}-thread")

        board = Board.objects.get(thread=daily)
        board.focus = SECRET
        board.state = [{"id": "1", "text": SECRET, "children": [], "data": {}}]
        board.save()
        Plan.objects.create(pub_date=cls.day, thread=daily, focus=SECRET)
        Reflection.objects.create(pub_date=cls.day, thread=daily, good=SECRET)

        cls.tag = JournalTag.objects.create(
            user=alice, name=f"{SECRET}-tag", slug="secret-habit"
        )
        cls.journal = JournalAdded.objects.create(
            thread=daily, comment=SECRET, published=now
        )
        cls.journal.tags.add(cls.tag)
        JournalAdded.objects.create(thread=secret_thread, comment=SECRET, published=now)
        cls.photo = PhotoAdded.objects.create(
            thread=daily,
            comment=SECRET,
            original_key=f"photos/{alice.pk}/a.jpg",
            content_type="image/jpeg",
            published=now,
        )
        cls.commit = BoardCommitted.objects.create(
            thread=daily, focus=SECRET, before=[], after=[], published=now
        )

        cls.habit = make_habit(alice, SECRET, slug="secret-habit", keywords=["secret"])
        HabitTracked.objects.create(
            habit=cls.habit, thread=daily, note=SECRET, published=now
        )

        obs_type = ObservationType.objects.create(name="Error", slug="error")
        # The add form preselects this type; production has it.
        ObservationType.objects.create(name="Observation", slug="observation")
        cls.observation = Observation.objects.create(
            user=alice,
            thread=daily,
            type=obs_type,
            pub_date=cls.day,
            situation=SECRET,
            interpretation=SECRET,
            approach=SECRET,
        )
        ObservationUpdated.objects.create(
            observation=cls.observation, comment=SECRET, published=now
        )
        to_close = Observation.objects.create(
            user=alice, thread=daily, type=obs_type, pub_date=cls.day, situation=SECRET
        )
        closed = close_observation(to_close.pk)
        cls.closed_stream_id = closed.event_stream_id
        insight = InsightRefined.from_observation_closed(closed)
        insight.approach = SECRET
        insight.save()

        breakthrough = Breakthrough.objects.create(
            user=alice, slug="2026", theme=SECRET, areas_of_concern=SECRET
        )
        cls.outcome = ProjectedOutcome.objects.create(
            breakthrough=breakthrough,
            name=SECRET,
            description=SECRET,
            resolved_by=datetime.date(2026, 12, 31),
        )

        cls.story = start_trip(alice, title=SECRET)
        add_trip_note(alice, cls.story.pk, SECRET, now)
        cls.share = share_trip(alice, cls.story.pk)

        cls.forbidden = [
            SECRET,
            str(cls.observation.event_stream_id),
            str(cls.closed_stream_id),
            str(cls.outcome.event_stream_id),
            str(daily.journal_stream_id),
            str(cls.story.event_stream_id),
        ]

    def setUp(self):
        self.client.force_login(self.bob)
        self.client.force_authenticate(user=self.bob)
        # Nothing here may reach S3.
        for name in ("object_exists", "download_bytes", "upload_bytes"):
            patcher = mock.patch(
                f"tasks.apps.tree.services.photos.storage.{name}",
                side_effect=AssertionError(f"storage.{name} called"),
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def url_kwargs(self, pattern):
        """Alice's objects, by URL parameter name."""
        values = {
            "id": self.commit.pk,
            "pk": self.journal.pk,
            "observation_id": self.observation.pk,
            "projected_outcome_id": self.outcome.pk,
            "story_id": self.story.pk,
            "event_id": self.photo.pk,
            "event_stream_id": self.closed_stream_id,
            "share_uuid": self.share.uuid,
            "stream_id": self.story.event_stream_id,
            "slug": self.habit.slug,
            "year": self.day.year,
            "month": self.day.month,
        }
        kwargs = {}
        for name in pattern.pattern.regex.groupindex:
            if name == "format":
                continue
            self.assertIn(
                name,
                values,
                f"{pattern.name}: URL parameter {name!r} unknown to this test",
            )
            kwargs[name] = values[name]
        return kwargs

    def payload(self):
        """Everything a write might take, pointing at Alice's objects."""
        return {
            "text": "bob",
            "comment": "bob",
            "thread": "Daily",
            "thread-name": "Daily",
            "tags": [],
            "observation": self.observation.pk,
            "other_observation_id": self.observation.pk,
            "other_event_stream_id": str(self.closed_stream_id),
            "story": self.story.pk,
            "story_id": self.story.pk,
            "projected_outcome": self.outcome.pk,
            "state": [],
            "focus": "bob",
            "good": "bob",
            "keyword": "secret",
            "date": self.day.isoformat(),
            "note": "bob",
            "key": f"photos/{self.alice.pk}/a.jpg",
            "content_type": "image/jpeg",
            "done": True,
            "action": "share",
            "username": "bob",
        }

    def alices_data(self):
        """A fingerprint of everything Alice has."""
        alice = self.alice
        streams = Event.objects.owned_by(alice).values("event_stream_id")
        return {
            "events": sorted(
                map(repr, Event.objects.owned_by(alice).values().order_by("pk"))
            ),
            "plans": list(Plan.objects.filter(thread__user=alice).values()),
            "reflections": list(Reflection.objects.filter(thread__user=alice).values()),
            "boards": list(Board.objects.filter(thread__user=alice).values()),
            "threads": list(Thread.objects.filter(user=alice).values()),
            "observations": list(Observation.objects.filter(user=alice).values()),
            "outcomes": list(ProjectedOutcome.objects.owned_by(alice).values()),
            "breakthroughs": list(Breakthrough.objects.filter(user=alice).values()),
            "stories": list(Story.objects.filter(user=alice).values()),
            "shares": list(SharedStory.objects.filter(story__user=alice).values()),
            "habits": list(Habit.objects.filter(user=alice).values()),
            "keywords": list(HabitKeyword.objects.filter(user=alice).values()),
            "profile": list(Profile.objects.filter(user=alice).values()),
            "access": sorted(
                EventStreamAccess.objects.filter(stream__created_by=alice).values_list(
                    "stream_id", "user_id", "role"
                )
            ),
            "entries": sorted(
                EventStreamEntry.objects.filter(stream__created_by=alice).values_list(
                    "stream_id", "event_id"
                )
            ),
            "events_in_alices_streams": Event.objects.filter(
                event_stream__in=streams
            ).count(),
        }

    def test_no_route_lets_another_user_see_or_change_alices_data(self):
        before = self.alices_data()
        checked = 0

        for route, name, pattern in _routes():
            if name in PUBLIC_ROUTES:
                continue
            url = "/" + route.lstrip("^").rstrip("$")
            for param, value in self.url_kwargs(pattern).items():
                url = url.replace(f"<int:{param}>", str(value))
                url = url.replace(f"<uuid:{param}>", str(value))
                url = url.replace(f"<slug:{param}>", str(value))
                url = url.replace(f"(?P<{param}>[^/.]+)", str(value))
            url = url.replace("^", "").replace("$", "")

            for method in METHODS:
                with self.subTest(route=name or url, method=method):
                    response = getattr(self.client, method)(
                        url, self.payload(), format="json"
                    )
                    self.assertLess(
                        response.status_code, 500, f"{method.upper()} {url}"
                    )
                    body = response.content.decode(errors="replace")
                    for value in self.forbidden:
                        self.assertNotIn(
                            value, body, f"{method.upper()} {url} shows {value}"
                        )
                    checked += 1

        self.assertGreater(checked, 400)
        self.assertEqual(self.alices_data(), before)

    def test_the_public_share_page_shows_only_the_shared_trip(self):
        response = self.client.get(f"/trips/shared/{self.share.uuid}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            str(self.observation.event_stream_id), response.content.decode()
        )
