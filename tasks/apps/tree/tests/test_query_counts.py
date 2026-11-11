"""Pages and API lists whose query count must not grow with what they show.

Each test opens a page with a row on it, adds two more, and opens it again:
the second time may take no more queries than the first.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from rest_framework.test import APITestCase

from ..models import (
    Event,
    HabitTracked,
    JournalAdded,
    JournalTag,
    Observation,
    ObservationAttached,
    ObservationEventMixin,
    ObservationMade,
    ObservationRecontextualized,
    ObservationReinterpreted,
    ObservationType,
    ObservationUpdated,
    Plan,
    Profile,
    Thread,
)
from ..services.journalling import habits_line_to_habits_tracked
from ..services.observations.closing import close_observation
from .factories import make_habit


class QueryCountTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.daily(cls.user)
        cls.now = timezone.now()
        cls.obs_type = ObservationType.objects.create(name="Error", slug="error")

    def setUp(self):
        self.client.force_login(self.user)
        self.client.force_authenticate(user=self.user)

    def count_queries(self, url, params, html):
        headers = {"HTTP_ACCEPT": "text/html"} if html else {}
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url, params, **headers)
        self.assertEqual(response.status_code, 200, url)
        return len(queries)

    def assert_constant_queries(self, url, add, params=None, html=False):
        """``add(n)`` puts one more row on the page at ``url``."""
        add(0)
        # Warms up per-process caches, such as polymorphic content types.
        self.count_queries(url, params, html)
        one = self.count_queries(url, params, html)

        add(1)
        add(2)

        # Fewer is fine: once a paginated list fills its page, some kinds of
        # event may drop off it, and their query with them.
        self.assertLessEqual(self.count_queries(url, params, html), one, url)

    # --- What the pages show ---

    def habit(self, n):
        return make_habit(
            self.user,
            f"Habit {n}",
            slug=f"habit-{n}",
            keywords=[f"alpha{n}", f"beta{n}"],
        )

    def track(self, habit):
        return HabitTracked.objects.create(
            habit=habit, thread=self.daily, published=self.now
        )

    def journal(self, n):
        entry = JournalAdded.objects.create(
            thread=self.daily, comment=f"entry {n}", published=self.now
        )
        entry.tags.add(
            JournalTag.objects.create(user=self.user, name=f"Tag {n}", slug=f"tag-{n}")
        )
        return entry

    def observation(self, situation):
        observation = Observation.objects.create(
            user=self.user,
            thread=self.daily,
            type=self.obs_type,
            pub_date=timezone.localdate(self.now),
            situation=situation,
        )
        ObservationMade.from_observation(observation, published=self.now).save()
        return observation

    def changed_observation(self, n):
        """An observation with an update and a reinterpretation, which are
        shown with the observation's situation."""
        observation = self.observation(f"changed {n}")
        ObservationUpdated.objects.create(
            observation=observation, comment=f"update {n}", published=self.now
        )
        ObservationReinterpreted.from_observation(
            observation, old="", published=self.now
        ).save()
        return observation

    def attach(self, complex_stream_id, n):
        """Attach an open and a closed observation to the complex one."""
        for other in (
            self.observation(f"open {n}"),
            close_observation(self.observation(f"closed {n}").pk),
        ):
            ObservationAttached.objects.create(
                thread=self.daily,
                event_stream_id=complex_stream_id,
                other_event_stream_id=other.event_stream_id,
                published=self.now,
            )

    # --- Habits ---

    def test_habit_list(self):
        self.assert_constant_queries("/habits/", self.habit)

    def test_habit_page(self):
        habit = self.habit("tracked")
        self.assert_constant_queries(
            f"/habits/{habit.slug}/", lambda n: self.track(habit)
        )

    def test_today_page(self):
        habit = self.habit("tracked")
        self.assert_constant_queries("/", lambda n: self.track(habit))

    def test_habit_api(self):
        self.assert_constant_queries("/habit-api/", self.habit)

    def test_habit_keywords(self):
        self.assert_constant_queries(
            "/habit/keywords/mine/", self.habit, params={"all": "true"}
        )

    def test_profile(self):
        profile = Profile.objects.get(user=self.user)

        def add(n):
            profile.habit_keywords.add(*self.habit(n).keywords.all())

        self.assert_constant_queries("/profile/", add)

    def test_hashtags_are_matched_in_one_query(self):
        for n in range(3):
            self.habit(n)

        with self.assertNumQueries(1):
            tracked = habits_line_to_habits_tracked("#alpha0 done #beta2", self.user)

        self.assertEqual(
            [habit.name for _, habit, _ in tracked], ["Habit 0", "Habit 2"]
        )

    # --- Events ---

    def test_event_archive(self):
        def add(n):
            self.track(self.habit(n))
            self.changed_observation(n)

        self.assert_constant_queries("/events/", add)

    def test_journal_api(self):
        self.assert_constant_queries("/journal/", self.journal)

    def test_daily_events_api(self):
        def add(n):
            self.journal(n)
            self.track(self.habit(n))
            self.changed_observation(n)

        self.assert_constant_queries(
            "/api/events/daily/",
            add,
            params={"date": timezone.localdate(self.now).isoformat()},
        )

    def test_observation_events_api(self):
        def add(n):
            self.changed_observation(n)
            close_observation(self.observation(f"closed {n}").pk)

        self.assert_constant_queries("/observation-events/", add)

    def test_events_show_the_situation_now_and_when_they_happened(self):
        observation = self.observation("first")
        reinterpreted = ObservationReinterpreted.from_observation(
            observation, old="", published=self.now + timedelta(minutes=1)
        )
        reinterpreted.save()
        observation.situation = "second"
        ObservationRecontextualized.from_observation(
            observation, old="first", published=self.now + timedelta(minutes=2)
        ).save()

        for prefetched in (False, True):
            with self.subTest(prefetched=prefetched):
                event = Event.objects.get(pk=reinterpreted.pk)
                if prefetched:
                    ObservationEventMixin.prefetch_situations([event])

                with self.assertNumQueries(0 if prefetched else 3):
                    self.assertEqual(event.situation(), "second")
                    self.assertEqual(event.situation_at_creation(), "first")

    def test_updates_browsable_api(self):
        self.assert_constant_queries(
            "/updates/", lambda n: self.observation(f"open {n}"), html=True
        )

    # --- Complex observations ---

    def test_open_complex_observation_page(self):
        complex = self.observation("complex")

        self.assert_constant_queries(
            f"/observations/{complex.pk}/",
            lambda n: self.attach(complex.event_stream_id, n),
        )

    def test_closed_complex_observation_pages(self):
        complex = self.observation("complex")
        stream_id = complex.event_stream_id
        close_observation(complex.pk)

        for url in (
            f"/observations/closed/{stream_id}/",
            f"/insights/{stream_id}/",
        ):
            with self.subTest(url=url):
                self.assert_constant_queries(url, lambda n: self.attach(stream_id, n))

    # --- The admin ---

    def test_admin_lists(self):
        self.client.force_login(
            get_user_model().objects.create_superuser(username="admin", password="x")
        )
        habit = self.habit("tracked")
        today = timezone.localdate(self.now)

        for url, add in (
            (
                "/admin/tree/plan/",
                lambda n: Plan.objects.create(
                    thread=self.daily, pub_date=today - timedelta(days=n)
                ),
            ),
            ("/admin/tree/habit/", self.habit),
            ("/admin/tree/habittracked/", lambda n: self.track(habit)),
        ):
            with self.subTest(url=url):
                self.assert_constant_queries(url, add)
