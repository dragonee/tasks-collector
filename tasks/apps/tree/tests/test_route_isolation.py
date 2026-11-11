"""Every route of the app keeps one user's data from another.

Alice has one of everything: what she keeps to herself carries SECRET, what
she may share carries SHARED. Bob calls every route with every method, with a
JSON body and with a form-encoded one, at each of Alice's objects the route
takes; every route without parameters he also calls with query strings naming
her objects, and every API route once more as a browser would (``Accept:
text/html``), so the browsable API renders its forms. He does it twice: as a
stranger, and as a viewer of the trip, observations and outcome Alice shares
with him.

Nothing he gets back may show what isn't his or shared with him, nothing may
fail with a server error, Alice's ids must answer like ids nobody has, and
afterwards Alice's data must be exactly as before. Last, Alice opens every page
herself: none may fail, and none may open a form inside another form.

A new route is covered automatically. A route whose URL takes parameters must
be given Alice's objects in ``targets``, by name (by path for an unnamed one):
until it is, the test fails.
"""

import datetime
import uuid
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
    ObservationMade,
    ObservationType,
    ObservationUpdated,
    PhotoAdded,
    Plan,
    PlanLine,
    Profile,
    ProjectedOutcome,
    Reflection,
    ReflectionLine,
    SharedStory,
    Story,
    Task,
    Thread,
)
from ..services.observations.closing import close_observation
from ..services.streams import share
from ..services.tasks.operations import complete
from ..services.today import plan_text
from ..services.trips import add_trip_note, share_trip, start_trip
from .factories import make_habit, make_plan, make_reflection, make_thread
from .html import nested_forms

SECRET = "ALICE-SECRET"
SHARED = "ALICE-SHARED"

# Reachable without logging in, by design: a share link is the capability.
PUBLIC_ROUTES = {"trip-shared-detail"}

METHODS = ("get", "post", "put", "patch", "delete")

# What an id nobody has looks like, by kind of value.
GHOST_INT = 999999
GHOST_UUID = uuid.UUID("00000000-0000-4000-8000-000000000000")
GHOST_SLUG = "no-such-slug"

# URL parameters that name a moment, not an object: nothing to compare with.
NOT_IDS = {"year", "month"}


def _routes(patterns=None, prefix=""):
    """(route, key, pattern) for every route served by the tree app; the key
    is the route's name, or its path when it has none.

    The router's format-suffix twins (``boards/<pk>.json``) are left out: they
    are the same views as the routes they double.
    """
    for pattern in patterns if patterns is not None else get_resolver().url_patterns:
        if isinstance(pattern, URLResolver):
            yield from _routes(pattern.url_patterns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            callback = pattern.callback
            view = getattr(callback, "cls", None) or getattr(
                callback, "view_class", callback
            )
            if not getattr(view, "__module__", "").startswith("tasks.apps.tree."):
                continue
            if "format" in pattern.pattern.regex.groupindex:
                continue
            route = (prefix + str(pattern.pattern)).replace("^", "").replace("$", "")
            yield route, pattern.name or route, pattern


def _url(route, kwargs):
    url = "/" + route
    for param, value in kwargs.items():
        for converter in ("int", "uuid", "slug"):
            url = url.replace(f"<{converter}:{param}>", str(value))
        url = url.replace(f"(?P<{param}>[^/.]+)", str(value))
    return url


def _ghost(kwargs):
    """``kwargs`` with every object id swapped for one nobody has."""
    ghost = {}
    for param, value in kwargs.items():
        if param in NOT_IDS:
            ghost[param] = value
        elif isinstance(value, uuid.UUID):
            ghost[param] = GHOST_UUID
        elif isinstance(value, int):
            ghost[param] = GHOST_INT
        elif value == "true":
            # A switch, such as attach_mode, not an object.
            ghost[param] = value
        else:
            ghost[param] = GHOST_SLUG
    return ghost


class RouteIsolationTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user(username="alice", password="x")
        cls.bob = User.objects.create_user(username="bob", password="x")
        alice = cls.alice
        # The wall clock: the today page, daily events and the current month's
        # archives show what happened now.
        now = timezone.now()
        cls.now = now
        cls.day = timezone.localdate(now)
        cls.daily = daily = Thread.objects.daily(alice)
        cls.secret_thread = make_thread(alice, f"{SECRET}-thread")

        cls.board = Board.objects.get(thread=daily)
        cls.board.focus = SECRET
        cls.board.state = [{"id": "1", "text": SECRET, "children": [], "data": {}}]
        cls.board.save()
        cls.plan = make_plan(daily, cls.day, SECRET)
        cls.reflection = make_reflection(daily, cls.day, good=SECRET)

        # A task of hers, planned for the day and done: its completion is an
        # event in the stream of her board.
        cls.task = plan_text(alice, f"{SECRET} task", Thread.DAILY, cls.day, cls.day)
        complete(cls.task, alice, day=cls.day, at=now)

        cls.tag = JournalTag.objects.create(
            user=alice, name=f"{SECRET}-tag", slug="secret-tag"
        )
        cls.journal = JournalAdded.objects.create(
            thread=daily, comment=SECRET, published=now
        )
        cls.journal.tags.add(cls.tag)
        JournalAdded.objects.create(
            thread=cls.secret_thread, comment=SECRET, published=now
        )
        cls.photo = cls._photo("standalone", SECRET)
        cls.commit = BoardCommitted.objects.create(
            thread=daily, focus=SECRET, before=[], after=[], published=now
        )

        cls.habit = make_habit(alice, SECRET, slug="secret-habit", keywords=["secret"])
        HabitTracked.objects.create(
            habit=cls.habit, thread=daily, note=SECRET, published=now
        )

        cls.obs_type = ObservationType.objects.create(name="Error", slug="error")
        # The add form preselects this type; production has it.
        ObservationType.objects.create(name="Observation", slug="observation")

        breakthrough = Breakthrough.objects.create(
            user=alice, slug=str(cls.day.year), theme=SECRET, areas_of_concern=SECRET
        )

        # One of each shareable thing to keep and one to share.
        cls.private = cls._shareables(SECRET, breakthrough)
        cls.shared = cls._shareables(SHARED, breakthrough)
        cls.share = share_trip(alice, cls.private["story"].pk)

    @classmethod
    def _photo(cls, name, text):
        return PhotoAdded.objects.create(
            thread=cls.daily,
            comment=text,
            original_key=f"photos/{cls.alice.pk}/{name}.jpg",
            content_type="image/jpeg",
            published=cls.now,
        )

    @classmethod
    def _observation(cls, situation, **fields):
        """An open observation with the event that records it, as the app
        makes one."""
        observation = Observation.objects.create(
            user=cls.alice,
            thread=cls.daily,
            type=cls.obs_type,
            pub_date=cls.day,
            situation=situation,
            **fields,
        )
        made = ObservationMade.from_observation(
            observation, published=cls.now - datetime.timedelta(minutes=1)
        )
        made.save()
        return observation

    @classmethod
    def _shareables(cls, text, breakthrough):
        alice, daily, now = cls.alice, cls.daily, cls.now

        observation = cls._observation(text, interpretation=text, approach=text)
        update = ObservationUpdated.objects.create(
            observation=observation, comment=text, published=now
        )
        closed = close_observation(cls._observation(text).pk)
        insight = InsightRefined.from_observation_closed(closed)
        insight.approach = text
        insight.save()

        outcome = ProjectedOutcome.objects.create(
            breakthrough=breakthrough,
            name=text,
            description=text,
            resolved_by=datetime.date(cls.day.year, 12, 31),
        )

        story = start_trip(alice, title=text)
        note = add_trip_note(alice, story.pk, text, now)
        photo = cls._photo(f"trip-{text}", text)
        story.add(photo)

        return {
            "observation": observation,
            "update": update,
            "closed_stream": closed.event_stream,
            "outcome": outcome,
            "story": story,
            "trip_note": note,
            "trip_photo": photo,
        }

    def setUp(self):
        self.client.force_login(self.bob)
        self.client.force_authenticate(user=self.bob)
        # Nothing here may reach S3.
        for name in ("object_exists", "download_bytes", "upload_bytes"):
            self._patch(name, side_effect=AssertionError(f"storage.{name} called"))
        for name in (
            "presign_get",
            "presign_get_web",
            "presign_put",
            "presign_put_web",
        ):
            self._patch(name, side_effect=lambda key, *a, **kw: f"https://s/{key}")

    def _patch(self, name, **kwargs):
        patcher = mock.patch(
            f"tasks.apps.tree.services.photos.storage.{name}", **kwargs
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    # --- What the routes are pointed at ---

    def targets(self):
        """The objects of Alice's that each route with parameters is called
        with, by route name: (what it is, URL kwargs). "private" ones she keeps
        to herself, "shared" ones she shares in the viewer walk."""
        p, s = self.private, self.shared
        day = self.day

        def both(param, key, attr="pk"):
            return [
                ("private", {param: getattr(p[key], attr)}),
                ("shared", {param: getattr(s[key], attr)}),
            ]

        def private(**kwargs):
            return [("private", kwargs)]

        observation = both("observation_id", "observation")
        closed = both("event_stream_id", "closed_stream")
        story = both("story_id", "story")
        outcome = both("projected_outcome_id", "outcome")
        streams = self.stream_targets()
        task = private(task_id=self.task.pk)

        return {
            "task-detail": task,
            "task-plan": task,
            "task-unplan": task,
            "task-move": task,
            "task-complete": task,
            "task-reopen": task,
            "board-summary": private(id=self.commit.pk),
            "boards/<int:id>/commit/": private(id=self.board.pk),
            "public-habit-detail": private(slug=self.habit.slug),
            "android-trip-photo-original": both("event_id", "trip_photo"),
            "android-trip-detail": story,
            "android-photo-original": private(event_id=self.photo.pk),
            "public-observation-closed-detail": closed,
            "public-insight-edit": closed,
            "public-observation-edit": observation,
            "public-observation-close": observation,
            "public-observation-close-and-extract": observation,
            "public-observation-extract-insight": closed,
            "public-observation-attach": observation,
            "public-observation-detach": observation,
            "public-observation-attachments": observation,
            "public-observation-journalize": observation,
            "breakthrough": private(year=day.year),
            "projected-outcome-events-history": both(
                "event_stream_id", "outcome", "event_stream_id"
            ),
            "projected-outcome-close": outcome,
            "projected-outcome-move": outcome,
            "projected-outcome-evolve": outcome,
            "public-diary-archive-month": private(year=day.year, month=day.month),
            "journal-entry-tag": private(journal_id=self.journal.pk)
            + both("journal_id", "trip_note"),
            "public-diary-archive-current-month-tag": private(slug=self.tag.slug),
            "public-diary-archive-month-tag": private(
                slug=self.tag.slug, year=day.year, month=day.month
            ),
            "stream-sharing": streams,
            "stream-sharing-api": streams,
            "trip-shared-detail": private(share_uuid=self.share.uuid),
            "trip-detail": story,
            "trip-share": story,
            "trip-unshare": story,
            "trip-stop": story,
            "trip-add-note": story,
            "trip-photo-presign": story,
            "trip-photo-confirm": story,
            "public-event-archive-month": private(year=day.year, month=day.month),
            "boards-detail": private(pk=self.board.pk),
            "plan-detail": private(pk=self.plan.pk),
            "reflection-detail": private(pk=self.reflection.pk),
            "journaladded-detail": private(pk=self.journal.pk)
            + both("pk", "trip_note"),
            "observation-detail": both("pk", "observation"),
            "observationupdated-detail": both("pk", "update"),
            "event-detail": both("pk", "update"),
            "habit-detail": private(pk=self.habit.pk),
            "thread-detail": private(pk=self.secret_thread.pk),
            "profile-detail": private(pk=Profile.objects.get(user=self.alice).pk),
            "stories-detail": both("pk", "story"),
        }

    def stream_targets(self):
        p, s = self.private, self.shared
        streams = [
            ("private", p["story"].event_stream_id),
            ("private", p["observation"].event_stream_id),
            ("private", p["closed_stream"].pk),
            ("private", p["outcome"].event_stream_id),
            ("private", self.secret_thread.board_stream_id),
            ("private", self.daily.journal_stream_id),
            ("shared", s["story"].event_stream_id),
            ("shared", s["observation"].event_stream_id),
            ("shared", s["closed_stream"].pk),
            ("shared", s["outcome"].event_stream_id),
        ]
        return [(what, {"stream_id": stream_id}) for what, stream_id in streams]

    def queries(self):
        """Query strings for the routes without parameters: (what they name,
        the query, the same query naming nothing, or None if it names no
        object)."""
        queries = []
        for what, objects in (("private", self.private), ("shared", self.shared)):
            observation = objects["observation"]
            for query in (
                {"observation_id": observation.pk},
                {"observation": observation.pk},
                {"attach_mode": "true", "observation_id": observation.pk},
                {"event_stream_id": observation.event_stream_id},
                {"event_stream_id": objects["closed_stream"].pk},
                {"event_stream_id": objects["outcome"].event_stream_id},
                {"story": objects["story"].pk},
            ):
                queries.append((what, query, _ghost(query)))
        for query in (
            {"thread": self.secret_thread.pk},
            {"thread": self.secret_thread.name},
        ):
            queries.append(("private", query, _ghost(query)))
        for query in (
            {"q": "secret"},
            {"q": f"#{self.private['observation'].pk}"},
            {"date": self.day.isoformat()},
            {"features": "updates"},
            {"active": "true"},
            {"all": "true"},
            {"type": "error"},
            {"year": self.day.year},
            {"ownership": "all"},
        ):
            queries.append(("none", query, None))
        return queries

    def payloads(self):
        """Everything a write might take, pointing at Alice's objects: as an
        API client sends it (JSON, threads and tags by name) and as a browser
        form does (form-encoded, objects by id)."""
        p = self.private
        common = {
            "text": "bob",
            "comment": "bob",
            "title": "bob",
            "note": "bob",
            "focus": "bob",
            "good": "bob",
            "situation": "bob",
            "interpretation": "bob",
            "approach": "bob",
            "name": "bob",
            "description": "bob",
            "success_criteria": "bob",
            "thread-name": "Daily",
            "observation": p["observation"].pk,
            "other_observation_id": p["observation"].pk,
            "other_event_stream_id": str(p["closed_stream"].pk),
            "story": p["story"].pk,
            "story_id": p["story"].pk,
            "projected_outcome": p["outcome"].pk,
            "keyword": "secret",
            "date": self.day.isoformat(),
            "day": self.day.isoformat(),
            "from_date": self.day.isoformat(),
            "to_date": self.day.replace(day=1).isoformat(),
            "pub_date": self.day.isoformat(),
            "board_id": self.board.pk,
            "item_id": "1",
            "resolved_by": self.day.replace(month=12, day=31).isoformat(),
            "key": f"photos/{self.alice.pk}/standalone.jpg",
            "content_type": "image/jpeg",
            "done": True,
            "action": "share",
            "username": "bob",
        }
        json = common | {
            "thread": "Daily",
            "type": self.obs_type.slug,
            "tags": [],
            "state": [],
        }
        form = common | {
            "thread": Thread.objects.daily(self.bob).pk,
            "type": self.obs_type.pk,
            "tag": self.tag.pk,
            "journal": self.journal.pk,
            "next": "/",
            "observationupdated_set-TOTAL_FORMS": 0,
            "observationupdated_set-INITIAL_FORMS": 0,
            "observationupdated_set-MIN_NUM_FORMS": 0,
            "observationupdated_set-MAX_NUM_FORMS": 1000,
        }
        return {"json": json, "form": form}

    # --- What Bob may not see, and what must not change ---

    def forbidden(self, viewer):
        """What Bob may not find in any response: everything of Alice's, or as
        her viewer, everything she didn't share with him."""
        p, s = self.private, self.shared
        values = [
            SECRET,
            str(self.share.uuid),
            str(p["story"].event_stream_id),
            str(p["observation"].event_stream_id),
            str(p["closed_stream"].pk),
            str(p["outcome"].event_stream_id),
            str(self.daily.journal_stream_id),
            str(self.daily.board_stream_id),
            str(self.secret_thread.board_stream_id),
            str(self.habit.event_stream_id),
        ]
        if not viewer:
            values += [
                SHARED,
                "alice",
                str(s["story"].event_stream_id),
                str(s["observation"].event_stream_id),
                str(s["closed_stream"].pk),
                str(s["outcome"].event_stream_id),
            ]
        return values

    def alices_data(self):
        """A fingerprint of everything Alice has."""
        alice = self.alice
        streams = Event.objects.owned_by(alice).values("event_stream_id")
        return {
            "events": sorted(
                map(repr, Event.objects.owned_by(alice).values().order_by("pk"))
            ),
            "plans": list(Plan.objects.filter(thread__user=alice).values()),
            "tasks": list(Task.objects.filter(user=alice).values()),
            "plan_lines": list(
                PlanLine.objects.filter(plan__thread__user=alice).values()
            ),
            "reflection_lines": list(
                ReflectionLine.objects.filter(reflection__thread__user=alice).values()
            ),
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
            "tags": list(JournalTag.objects.filter(user=alice).values()),
            "taggings": sorted(
                JournalTag.journals.through.objects.filter(
                    journaltag__user=alice
                ).values_list("journaltag_id", "journaladded_id")
            ),
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

    # --- The walks ---

    def call(self, method, url, body=None, query=None, html=False):
        """One request. GETs take a query string; the other methods a body,
        "json" or "form" (form-encoded, as a browser posts)."""
        headers = {"HTTP_ACCEPT": "text/html"} if html else {}
        if method == "get":
            return self.client.get(url, query or {}, **headers)
        data = self.payloads()[body]
        format = "json" if body == "json" else "multipart"
        return getattr(self.client, method)(url, data, format=format, **headers)

    def variants(self, method, api):
        """(body, html) for each way a method is called: GETs plainly, and as
        a browser to an API route, so the browsable API renders its forms; the
        others with each body."""
        if method == "get":
            return [(None, False), (None, True)] if api else [(None, False)]
        return [("json", False), ("form", False)]

    def check(self, response, request, forbidden, sent=()):
        """No server error, nothing ``forbidden`` and no form in a form. What
        Bob ``sent`` in the URL he may get back, as the browsable API does
        when it shows the request."""
        self.assertLess(response.status_code, 500, request)
        body = response.content.decode(errors="replace")
        for value in map(str, sent):
            # Long values only: ids and names, never a digit that is part of
            # a uuid.
            if len(value) >= 8:
                body = body.replace(value, "")
        for value in forbidden:
            self.assertNotIn(value, body, f"{request} shows {value}")
        if "html" in response.get("Content-Type", ""):
            self.assertEqual(nested_forms(body), [], f"{request} nests a form")

    def walk(self, viewer):
        """Bob calls everything; returns how many requests were checked.

        Only a viewer is pointed at what Alice shares: until she does, it is
        just more of what she keeps to herself. Only her private objects are
        compared with ids nobody has, since a viewer may open shared ones.
        """
        forbidden = self.forbidden(viewer)
        targets = self.targets()
        pointed_at = {"none", "private", "shared"} if viewer else {"none", "private"}
        checked = 0

        for route, key, pattern in _routes():
            if key in PUBLIC_ROUTES:
                continue
            params = set(pattern.pattern.regex.groupindex)
            if params:
                self.assertIn(
                    key, targets, f"{key}: URL parameters unknown to this test"
                )
                route_targets = targets[key]
            else:
                route_targets = [("none", {})]
            route_targets = [t for t in route_targets if t[0] in pointed_at]
            names_objects = bool(params - NOT_IDS)
            api = hasattr(pattern.callback, "cls")

            for method in METHODS:
                for body, html in self.variants(method, api):
                    how = "html" if html else body or "plain"
                    if names_objects:
                        ghost = _url(route, _ghost(route_targets[0][1]))
                        unknown = self.call(method, ghost, body, html=html)
                    for what, kwargs in route_targets:
                        url = _url(route, kwargs)
                        request = f"{method.upper()} {url} ({how})"
                        with self.subTest(request=request):
                            response = self.call(method, url, body, html=html)
                            self.check(response, request, forbidden, kwargs.values())
                            if names_objects and what == "private":
                                self.assertEqual(
                                    response.status_code,
                                    unknown.status_code,
                                    f"{request} answers unlike {ghost}",
                                )
                        checked += 1

            if params:
                continue
            url = _url(route, {})
            for what, query, ghost_query in self.queries():
                if what not in pointed_at:
                    continue
                request = f"GET {url} {query}"
                with self.subTest(request=request):
                    response = self.call("get", url, query=query)
                    self.check(response, request, forbidden, query.values())
                    if ghost_query is not None and what == "private":
                        unknown = self.call("get", url, query=ghost_query)
                        self.assertEqual(
                            response.status_code,
                            unknown.status_code,
                            f"{request} answers unlike {ghost_query}",
                        )
                checked += 1

        return checked

    def test_a_stranger_sees_and_changes_nothing_of_alices(self):
        before = self.alices_data()

        checked = self.walk(viewer=False)

        self.assertGreater(checked, 1800)
        self.assertEqual(self.alices_data(), before)

    def test_a_viewer_sees_only_what_is_shared_and_changes_nothing(self):
        s = self.shared
        for stream in (
            s["story"].event_stream,
            s["observation"].event_stream,
            s["closed_stream"],
            s["outcome"].event_stream,
        ):
            share(self.alice, stream, "bob")
        before = self.alices_data()

        checked = self.walk(viewer=True)

        self.assertGreater(checked, 2400)
        self.assertEqual(self.alices_data(), before)

    def test_every_page_of_the_owner_renders_without_nesting_forms(self):
        self.client.force_login(self.alice)
        self.client.force_authenticate(user=self.alice)
        targets = self.targets()

        for route, key, pattern in _routes():
            for _, kwargs in targets.get(key, [("none", {})]):
                url = _url(route, kwargs)
                for _, html in self.variants("get", hasattr(pattern.callback, "cls")):
                    with self.subTest(url=url, html=html):
                        response = self.call("get", url, html=html)
                        self.check(response, f"GET {url}", forbidden=[])

    def test_the_public_share_page_shows_only_the_shared_trip(self):
        response = self.client.get(f"/trips/shared/{self.share.uuid}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            str(self.private["observation"].event_stream_id),
            response.content.decode(),
        )
