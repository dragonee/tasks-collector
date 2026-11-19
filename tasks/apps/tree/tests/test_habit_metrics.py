"""What a habit records with each entry: its metrics, read from the notes as
tokens and written into them."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Habit, HabitMetric, HabitTracked, Thread
from ..services.habits import metrics
from .factories import make_habit, make_token

User = get_user_model()


def metric(key, kind="number", unit="", decimals=0):
    return SimpleNamespace(key=key, kind=kind, unit=unit, decimals=decimals)


WEIGHT = metric("weight", unit="kg", decimals=1)
STEPS = metric("steps")
DURATION = metric("duration", kind="duration")
PRESSURE = metric("pressure", kind="pressure")
AMOUNT = metric("amount", kind="money")


class ReadTest(SimpleTestCase):
    def test_each_kind_reads_its_form(self):
        note = (
            "#health 7000 kroków (steps=7000 weight=80.5kg duration=22m30s"
            " pressure=120/80 amount=90EUR)"
        )
        self.assertEqual(
            metrics.read(note, [WEIGHT, STEPS, DURATION, PRESSURE, AMOUNT]),
            {
                "steps": 7000,
                "weight": 80.5,
                "duration": 1350,
                "pressure": [120, 80],
                "amount": {"amount": 90, "currency": "EUR"},
            },
        )

    def test_only_the_keys_the_habit_records(self):
        self.assertEqual(metrics.read("steps=7000 kcal=2000", [STEPS]), {"steps": 7000})

    def test_a_token_in_another_unit_or_form_is_not_read(self):
        self.assertEqual(metrics.read("weight=80lb", [WEIGHT]), {})
        self.assertEqual(metrics.read("duration=45", [DURATION]), {})
        self.assertEqual(metrics.read("amount=90", [AMOUNT]), {})

    def test_a_token_stands_on_its_own(self):
        self.assertEqual(
            metrics.read("https://example.com/watch?v=4dSL", [metric("v")]), {}
        )
        self.assertEqual(metrics.read("xsteps=7000", [STEPS]), {})
        self.assertEqual(metrics.read("steps=7000x", [STEPS]), {})

    def test_the_first_token_of_a_key_counts(self):
        self.assertEqual(metrics.read("steps=1 steps=2", [STEPS]), {"steps": 1})

    def test_a_note_without_tokens_reads_nothing(self):
        self.assertEqual(metrics.read(None, [STEPS]), {})
        self.assertEqual(metrics.read("#health walked", [STEPS]), {})


class WriteTest(SimpleTestCase):
    def test_values_go_after_the_text_in_parentheses(self):
        self.assertEqual(
            metrics.write("Bike ride", [DURATION], {"duration": 2700}),
            "Bike ride (duration=45m)",
        )

    def test_without_text_the_tokens_are_the_note(self):
        self.assertEqual(
            metrics.write("", [WEIGHT, STEPS], {"weight": 80.5, "steps": 7000}),
            "weight=80.5kg steps=7000",
        )

    def test_a_value_takes_the_place_of_the_token_the_note_had(self):
        self.assertEqual(
            metrics.write("ran (duration=10m)", [DURATION], {"duration": 750}),
            "ran (duration=12m30s)",
        )

    def test_each_kind_is_written_as_it_is_read(self):
        values = {
            "weight": 80.5,
            "duration": 3605,
            "pressure": [120, 80],
            "amount": {"amount": 289323, "currency": "KZT"},
        }
        note = metrics.write("x", [WEIGHT, DURATION, PRESSURE, AMOUNT], values)
        self.assertEqual(
            note, "x (weight=80.5kg duration=60m5s pressure=120/80 amount=289323KZT)"
        )
        self.assertEqual(
            metrics.read(note, [WEIGHT, DURATION, PRESSURE, AMOUNT]), values
        )

    def test_a_number_keeps_its_metrics_decimals(self):
        self.assertEqual(metrics.token(WEIGHT, 80), "weight=80kg")
        self.assertEqual(metrics.token(WEIGHT, 80.25), "weight=80.2kg")


class CleanTest(SimpleTestCase):
    def test_values_a_client_sends(self):
        self.assertEqual(metrics.clean(WEIGHT, 80.46), 80.5)
        self.assertEqual(metrics.clean(STEPS, 7000), 7000)
        self.assertEqual(metrics.clean(DURATION, 1350), 1350)
        self.assertEqual(metrics.clean(PRESSURE, [120, 80]), [120, 80])
        self.assertEqual(
            metrics.clean(AMOUNT, {"amount": 90, "currency": "EUR"}),
            {"amount": 90, "currency": "EUR"},
        )

    def test_a_value_that_does_not_fit_is_refused(self):
        for bad_metric, raw in (
            (WEIGHT, "heavy"),
            (WEIGHT, True),
            (DURATION, -1),
            (DURATION, 1.5),
            (PRESSURE, [80, 120]),
            (PRESSURE, 120),
            (AMOUNT, {"amount": 90, "currency": "euro"}),
            (AMOUNT, 90),
        ):
            with self.subTest(metric=bad_metric.key, raw=raw):
                with self.assertRaises(ValidationError):
                    metrics.clean(bad_metric, raw)


class ShownTest(SimpleTestCase):
    def test_values_for_people(self):
        self.assertEqual(metrics.shown(WEIGHT, 80.5), "80.5 kg")
        self.assertEqual(metrics.shown(STEPS, 7000), "7000")
        self.assertEqual(metrics.shown(DURATION, 1350), "22 min 30 s")
        self.assertEqual(metrics.shown(DURATION, 3900), "1 h 5 min")
        self.assertEqual(metrics.shown(PRESSURE, [120, 80]), "120/80")
        self.assertEqual(
            metrics.shown(AMOUNT, {"amount": 90, "currency": "EUR"}), "90 EUR"
        )


class ValuesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")
        cls.habit = make_habit(cls.user, "Run", keywords=["run"])

    def _entry(self, note):
        return HabitTracked.objects.create(
            habit=self.habit,
            note=note,
            thread=Thread.objects.daily(self.user),
            published=timezone.now(),
        )

    def test_an_entry_keeps_what_its_habits_metrics_read(self):
        HabitMetric.objects.create(habit=self.habit, key="distance", unit="km")
        entry = self._entry("#run (distance=5km duration=30m)")
        self.assertEqual(entry.values, {"distance": 5})

        entry.note = "#run (distance=7km)"
        entry.save(update_fields=["note"])
        entry.refresh_from_db()
        self.assertEqual(entry.values, {"distance": 7})

    def test_a_new_metric_reads_the_entries_already_there(self):
        entry = self._entry("#run (distance=5km duration=30m)")
        self.assertEqual(entry.values, {})

        HabitMetric.objects.create(habit=self.habit, key="duration", kind="duration")
        entry.refresh_from_db()
        self.assertEqual(entry.values, {"duration": 1800})

        self.habit.metrics.filter(key="duration").delete()
        entry.refresh_from_db()
        self.assertEqual(entry.values, {})

    def test_a_habit_goes_with_its_metrics(self):
        HabitMetric.objects.create(habit=self.habit, key="distance", unit="km")
        self._entry("#run (distance=5km)")
        pk = self.habit.pk
        self.habit.delete()
        self.assertFalse(HabitMetric.objects.filter(habit_id=pk).exists())

    def test_a_journal_hashtag_gets_its_values(self):
        HabitMetric.objects.create(habit=self.habit, key="distance", unit="km")
        response = self._client().post(
            reverse("public-habit-track"),
            {"text": "#run park (distance=5km)"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            HabitTracked.objects.get(habit=self.habit).values, {"distance": 5}
        )

    def _client(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.user)
        return client

    def test_a_new_users_weight_habit_records_weight(self):
        weight = Habit.objects.get(user=self.user, slug="weight")
        self.assertEqual(
            list(weight.metrics.values_list("key", "kind", "unit", "decimals")),
            [("weight", "number", "kg", 1)],
        )


class TrackedHabitAPITest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")
        cls.token = make_token(cls.user)
        cls.habit = make_habit(cls.user, "Run", keywords=["run", "running"])
        HabitMetric.objects.create(
            habit=cls.habit, key="distance", unit="km", decimals=1
        )
        HabitMetric.objects.create(habit=cls.habit, key="duration", kind="duration")
        cls.url = reverse("habit-tracked-create")

    def setUp(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_an_entry_with_values_each_time(self):
        body = {
            "keyword": "running",
            "note": "park",
            "values": {"distance": 5.04, "duration": 1525},
            "published": "2026-11-18T07:30:00+01:00",
        }
        first = self.client.post(self.url, body, format="json")
        self.client.post(self.url, body, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.json()["note"], "park (distance=5km duration=25m25s)")
        self.assertEqual(first.json()["values"], {"distance": 5, "duration": 1525})
        self.assertEqual(HabitTracked.objects.filter(habit=self.habit).count(), 2)
        entry = HabitTracked.objects.filter(habit=self.habit).first()
        self.assertEqual(entry.thread, Thread.objects.daily(self.user))
        self.assertEqual(entry.created_by, self.user)

    def test_sent_again_with_its_key_it_gives_back_the_first(self):
        body = {"keyword": "run", "values": {"distance": 3}, "idempotency_key": "k1"}
        first = self.client.post(self.url, body, format="json")
        again = self.client.post(self.url, body, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assertEqual(HabitTracked.objects.filter(habit=self.habit).count(), 1)

    def test_a_value_the_habit_does_not_record_is_refused(self):
        response = self.client.post(
            self.url,
            {"keyword": "run", "values": {"weight": 80, "duration": "long"}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.json()["values"]), {"weight", "duration"})
        self.assertFalse(HabitTracked.objects.exists())

    def test_someone_elses_keyword_is_refused(self):
        bob = User.objects.create_user(username="bob", password="x")
        make_habit(bob, "Swim", keywords=["swim"])
        response = self.client.post(self.url, {"keyword": "swim"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_day_endpoint_takes_values_too(self):
        response = self.client.post(
            reverse("track-habit-api"),
            {"keyword": "run", "date": "2026-11-18", "values": {"distance": 4.2}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = HabitTracked.objects.get(habit=self.habit)
        self.assertEqual(entry.note, "distance=4.2km")
        self.assertEqual(entry.values, {"distance": 4.2})

    def test_the_activity_list_keeps_habits_tracked_today(self):
        self.client.post(self.url, {"keyword": "run"}, format="json")
        url = reverse("my-habit-keywords")

        offered = [item["keyword"] for item in self.client.get(url).json()]
        kept = [
            item["keyword"]
            for item in self.client.get(url, {"with_tracked": "true"}).json()
        ]

        self.assertNotIn("run", offered)
        self.assertIn("run", kept)

    def test_the_habits_a_phone_offers_say_what_they_record(self):
        response = self.client.get(reverse("my-habit-keywords"), {"all": "true"})
        run = next(item for item in response.json() if item["keyword"] == "run")
        self.assertEqual(
            run["habit"]["metrics"],
            [
                {
                    "key": "distance",
                    "label": "",
                    "kind": "number",
                    "unit": "km",
                    "decimals": 1,
                },
                {
                    "key": "duration",
                    "label": "",
                    "kind": "duration",
                    "unit": "",
                    "decimals": 0,
                },
            ],
        )


class HabitPageMetricsTest(TestCase):
    """The habit's page shows what its entries recorded; it changes nothing."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")
        cls.habit = make_habit(cls.user, "Run", keywords=["run"])
        cls.url = reverse("public-habit-detail", args=["run"])

    def setUp(self):
        self.client.force_login(self.user)

    def test_the_latest_value_is_shown_for_people(self):
        HabitMetric.objects.create(
            habit=self.habit, key="distance", label="Distance", unit="km", decimals=1
        )
        HabitMetric.objects.create(habit=self.habit, key="pace", label="Pace")
        HabitTracked.objects.create(
            habit=self.habit,
            note="#run (distance=5.5km)",
            thread=Thread.objects.daily(self.user),
            published=timezone.now(),
        )
        page = self.client.get(self.url)
        self.assertContains(page, "5.5 km")
        self.assertContains(page, "Nothing recorded yet.")
        self.assertContains(page, f"{reverse('metric-add')}?habit=run")
        self.assertNotContains(page, "delete_metric")

    def entry(self, note="#run (distance=5.5km)"):
        return HabitTracked.objects.create(
            habit=self.habit,
            note=note,
            thread=Thread.objects.daily(self.user),
            published=timezone.now(),
        )

    def test_a_habit_with_metrics_opens_on_them(self):
        HabitMetric.objects.create(habit=self.habit, key="distance", unit="km")
        self.entry()
        page = self.client.get(self.url)
        self.assertEqual(page.context["tab"], "metrics")
        self.assertContains(page, 'class="active" aria-current="page">Metrics<')
        self.assertNotContains(page, 'class="habit-month"')
        month = timezone.now().strftime("%Y-%m")
        self.assertContains(page, f'href="?tab=history#{month}"')

    def test_a_habit_without_metrics_has_only_its_history(self):
        self.entry()
        for query in ({}, {"tab": "metrics"}):
            page = self.client.get(self.url, query)
            self.assertEqual(page.context["tab"], "history")
            self.assertContains(page, 'class="habit-month"')
            self.assertNotContains(page, 'href="?tab=metrics"')
            self.assertNotContains(page, 'id="metrics"')
        month = timezone.now().strftime("%Y-%m")
        self.assertContains(page, f'href="#{month}"')

    def test_a_tab_is_chosen_by_the_link(self):
        HabitMetric.objects.create(habit=self.habit, key="distance", unit="km")
        self.entry()
        page = self.client.get(self.url, {"tab": "history"})
        self.assertEqual(page.context["tab"], "history")
        self.assertContains(page, 'class="habit-month"')
        page = self.client.get(self.url, {"tab": "elsewhere"})
        self.assertEqual(page.context["tab"], "metrics")

    def test_the_page_changes_nothing(self):
        response = self.client.post(
            self.url, {"label": "D", "key": "d", "kind": "number", "decimals": 0}
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(self.habit.metrics.exists())


class MetricsPageTest(TestCase):
    """The Metrics page: every metric by key, with the habits that record it;
    the New metric page adds one."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")
        cls.habit = make_habit(cls.user, "Run", keywords=["run"])
        cls.url = reverse("metrics")

    def setUp(self):
        self.client.force_login(self.user)

    def add(self, **fields):
        data = {"habit": self.habit.pk, "kind": "number", "decimals": 0}
        return self.client.post(reverse("metric-add"), {**data, **fields})

    def test_a_metric_added_reads_the_entries_and_counts_them(self):
        HabitTracked.objects.create(
            habit=self.habit,
            note="#run (distance=5.5km)",
            thread=Thread.objects.daily(self.user),
            published=timezone.now(),
        )
        response = self.add(label="Distance", key="distance", unit="km", decimals=1)
        self.assertRedirects(response, f"{self.url}#metric-distance")

        page = self.client.get(self.url)
        self.assertContains(page, 'id="metric-distance"')
        self.assertContains(page, "Number in km, 1 decimal")
        self.assertContains(page, "1 entry")
        habit_page = self.client.get(reverse("public-habit-detail", args=["run"]))
        self.assertContains(habit_page, "5.5 km")

    def test_a_key_lists_every_habit_that_records_it(self):
        walk = make_habit(self.user, "Walk", keywords=["walk"])
        HabitMetric.objects.create(habit=self.habit, key="distance", label="Run")
        HabitMetric.objects.create(habit=walk, key="distance", label="Walked")
        for note in ("#walk distance=2", "#walk distance=3"):
            HabitTracked.objects.create(
                habit=walk,
                note=note,
                thread=Thread.objects.daily(self.user),
                published=timezone.now(),
            )
        page = self.client.get(self.url)
        uses = page.context["keys"]["distance"]
        self.assertEqual(
            [(use.metric.habit.name, use.entries) for use in uses],
            [("Run", 0), ("Walk", 2)],
        )
        self.assertContains(page, "0 entries")
        self.assertContains(page, "2 entries")

    def test_a_metric_that_does_not_fit_is_refused(self):
        HabitMetric.objects.create(habit=self.habit, key="distance", unit="km")
        response = self.add(label="Again", key="distance")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Run already records distance.")

        response = self.add(label="Time", key="time", kind="duration", unit="min")
        self.assertContains(response, "Only a number has a unit.")
        self.assertEqual(self.habit.metrics.count(), 1)

    def test_a_metric_taken_away(self):
        distance = HabitMetric.objects.create(habit=self.habit, key="distance")
        response = self.client.post(self.url, {"delete_metric": distance.pk})
        self.assertRedirects(response, self.url)
        self.assertFalse(self.habit.metrics.exists())

    def test_the_habit_page_link_chooses_the_habit(self):
        make_habit(self.user, "Another", keywords=["another"])
        page = self.client.get(reverse("metric-add"), {"habit": "run"})
        self.assertEqual(page.context["form"]["habit"].value(), self.habit.pk)

    def test_the_list_links_to_the_form_from_its_header(self):
        page = self.client.get(self.url)
        self.assertNotContains(page, 'name="key"')
        self.assertContains(
            page, f'<a href="{reverse("metric-add")}" class="topbar-action on-right">'
        )

    def test_someone_elses_habit_cannot_be_chosen(self):
        bob = User.objects.create_user(username="bob", password="x")
        self.client.force_login(bob)
        response = self.add(label="D", key="d")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.habit.metrics.exists())

    def test_someone_elses_metric_cannot_be_taken_away(self):
        distance = HabitMetric.objects.create(habit=self.habit, key="distance")
        bob = User.objects.create_user(username="bob", password="x")
        self.client.force_login(bob)
        self.client.post(self.url, {"delete_metric": distance.pk})
        self.assertTrue(HabitMetric.objects.filter(pk=distance.pk).exists())

    def test_someone_elses_metrics_are_not_listed(self):
        HabitMetric.objects.create(habit=self.habit, key="distance")
        bob = User.objects.create_user(username="bob", password="x")
        self.client.force_login(bob)
        page = self.client.get(self.url)
        self.assertNotIn("distance", page.context["keys"])
