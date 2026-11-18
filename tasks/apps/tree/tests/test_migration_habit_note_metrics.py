"""0106: habit notes get their numbers written as tokens, and body weight
written under health moves to the weight habit.

The notes here are made up: the ones the migration fixes are someone's own,
and it knows them by digest only."""

import importlib
from unittest import mock

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase

BEFORE = [("tree", "0105_board_thread_required")]
AFTER = [("tree", "0106_habit_note_metrics")]

rules = importlib.import_module("tasks.apps.tree.migrations.0106_habit_note_metrics")


def rewrite(note, habit):
    return rules.enhance(rules.read_note(note, habit))


def buckets(note, habit):
    reading = rules.read_note(note, habit)
    found = [value.key for finding in reading.findings for value in finding.values]
    return found, [reading.note[start:end] for start, end in reading.unknown]


def fixes(*entries):
    """FIXES with only these (entry id, note, fix) in it."""
    return mock.patch.dict(
        rules.FIXES,
        {pk: (rules.digest(note), fix) for pk, note, fix in entries},
        clear=True,
    )


class ProseTest(SimpleTestCase):
    def test_a_number_in_prose_gets_its_token_after_the_note(self):
        self.assertEqual(
            rewrite("#health 7000 kroków", "health"), "#health 7000 kroków (steps=7000)"
        )
        self.assertEqual(
            rewrite("#health przebiegłem 7.5km", "health"),
            "#health przebiegłem 7.5km (distance=7.5km)",
        )

    def test_blood_pressure_is_one_metric_of_two_numbers(self):
        self.assertEqual(
            rewrite("#health 120/80 - blood pressure", "health"),
            "#health 120/80 - blood pressure (pressure=120/80)",
        )
        self.assertEqual(
            rules.tokens_in("(pressure=120/80)"), [("pressure", "120/80", "mmHg")]
        )

    def test_kilograms_are_body_weight_on_health_and_a_load_on_workout(self):
        self.assertEqual(
            rewrite("#health 80.5kg", "health"), "#health 80.5kg (weight=80.5kg)"
        )
        self.assertEqual(
            rewrite("#siłka 60kg sztanga", "workout"),
            "#siłka 60kg sztanga (load=60kg)",
        )

    def test_values_of_one_note_go_in_one_parenthesis(self):
        self.assertEqual(
            rewrite("#siłka 15km / 2h 30m", "workout"),
            "#siłka 15km / 2h 30m (distance=15km duration=150m)",
        )

    def test_a_currency_becomes_the_unit(self):
        self.assertEqual(
            rewrite("#spent 90 EUR na książki", "spent"),
            "#spent 90 EUR na książki (amount=90EUR)",
        )
        self.assertEqual(
            rewrite("#spent 289 323 KZT", "spent"),
            "#spent 289 323 KZT (amount=289323KZT)",
        )

    def test_money_put_aside_is_not_an_amount_spent(self):
        note = "#breakthrough odłożyłem 1000zł"
        self.assertEqual(rewrite(note, "breakthrough"), note)


class TokenTest(SimpleTestCase):
    def test_a_token_in_the_form_the_code_reads_stays(self):
        note = "steps=5000 distance=3.5km active=80min kcal=2000"
        self.assertEqual(rewrite(note, "health"), note)
        self.assertEqual(
            rewrite("#weight weight=80.5kg", "weight"), "#weight weight=80.5kg"
        )

    def test_a_token_in_an_older_form_is_rewritten_in_place(self):
        self.assertEqual(
            rewrite("#running distance=3.0km, time=22m30s", "workout"),
            "#running distance=3.0km, duration=22m30s",
        )
        self.assertEqual(
            rewrite("#workout Bike ride (duration=45 min)", "workout"),
            "#workout Bike ride (duration=45m)",
        )

    def test_a_duration_is_read_as_minutes_and_seconds(self):
        self.assertEqual(
            rules.tokens_in("#focus duration=50m5s x"), [("duration", "3005", "s")]
        )
        self.assertEqual(rules.tokens_in("active=80min"), [("active", "80", "min")])

    def test_a_note_with_tokens_is_read_from_them_alone(self):
        note = "#siłka 6km (30min na 4km) (distance=6km)"
        reading = rules.read_note(note, "workout")
        self.assertEqual(
            [value.token for value in rules.metric_values(reading)], ["distance=6km"]
        )
        self.assertEqual(rules.enhance(reading), note)

    def test_a_second_run_changes_nothing(self):
        for note, habit in (
            ("#health 7000 kroków", "health"),
            ("#health 120/80", "health"),
            ("#focus time=50m5s Raport", "focus"),
        ):
            once = rewrite(note, habit)
            self.assertEqual(rewrite(once, habit), once)

    def test_what_the_code_reads_back_is_what_was_found(self):
        note = "#health 15000 kroków, czyli 10 kilometrów"
        reading = rules.read_note(note, "health")
        self.assertEqual(
            rules.tokens_in(rules.enhance(reading)),
            sorted(value.written for value in rules.metric_values(reading)),
        )


class ConflictTest(SimpleTestCase):
    def test_a_metric_named_twice_leaves_the_note_as_it_is(self):
        note = "#siłka 3km biegu, 4km rowerem"
        self.assertEqual(
            rules.conflicts(rules.read_note(note, "workout")), ["distance"]
        )
        self.assertEqual(rewrite(note, "workout"), note)

    def test_a_fix_settles_a_conflict(self):
        note = "#siłka 3km biegu, 4km rowerem"
        with fixes((1, note, rules.append("distance=7km"))):
            reading = rules.read_note(rules.fixed(1, note), "workout")
        self.assertEqual(rules.conflicts(reading), [])
        self.assertEqual(rules.enhance(reading), f"{note} (distance=7km)")

    def test_a_fix_keeps_the_last_of_several_readings(self):
        self.assertEqual(
            rules.the_last_reading("#health 150/95 i 120/80"),
            "#health 150/95 i 120/80 (pressure=120/80)",
        )

    def test_a_fix_can_put_a_typo_right(self):
        with fixes((1, "#siłka 2kg biegu", rules.replace("2kg", "2km"))):
            self.assertEqual(rules.fixed(1, "#siłka 2kg biegu"), "#siłka 2km biegu")

    def test_a_fix_leaves_a_note_that_has_changed_since(self):
        with fixes((1, "#siłka 2kg biegu", rules.replace("2kg", "2km"))):
            self.assertEqual(rules.fixed(1, "#siłka 60kg"), "#siłka 60kg")
            self.assertEqual(rules.fixed(2, "#siłka 2kg biegu"), "#siłka 2kg biegu")


class BucketTest(SimpleTestCase):
    def test_numbers_that_measure_nothing_are_text(self):
        self.assertEqual(
            buckets("#til https://example.com/watch?v=4dSLx2", "til"), (["text"], [])
        )
        self.assertEqual(
            buckets("#spotkania Team42 standup", "spotkania"), (["text"], [])
        )

    def test_what_no_rule_takes_is_unknown(self):
        self.assertEqual(buckets("#health 15-20k kroków", "health"), ([], ["15", "20"]))
        self.assertEqual(buckets("#til 15h to dużo", "til"), ([], ["15"]))

    def test_a_time_of_day_near_waking_up_is_wake(self):
        found, _ = buckets(
            "#samopoczucie wstałem o 7, a budzik dzwonił wcześniej, bo na 6:00",
            "samopoczucie",
        )
        self.assertEqual(sorted(found), ["clock", "wake"])

    def test_coordinates_are_a_location_and_get_no_token(self):
        note = "#poi lat=52.0 lng=21.0"
        self.assertEqual(buckets(note, "poi"), (["location", "location"], []))
        self.assertEqual(rewrite(note, "poi"), note)


class HabitNoteMetricsMigrationTestCase(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        self.old_apps = executor.loader.project_state(BEFORE).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self, target=AFTER):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def _habits(self):
        """Every tracked habit as stored: its row, its event's row and its
        stream memberships, ids and times included."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT ht.*, e.* FROM tree_habittracked ht"
                " JOIN tree_event e ON e.id = ht.event_ptr_id ORDER BY e.id"
            )
            habits = cursor.fetchall()
            cursor.execute(
                "SELECT s.* FROM tree_eventstreamentry s"
                " JOIN tree_habittracked ht ON ht.event_ptr_id = s.event_id"
                " ORDER BY s.id"
            )
            return habits, cursor.fetchall()

    def _kept(self):
        """Whether the table of what the migration changed is there."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('tree_habittracked_before_0106')")
            return cursor.fetchone()[0] is not None

    def _model(self, name):
        return self.old_apps.get_model("tree", name)

    def _stream(self, user, type_):
        stream = self._model("EventStream").objects.create(type=type_, created_by=user)
        self._model("EventStreamAccess").objects.create(
            stream=stream, user=user, role="owner"
        )
        return stream

    def _user(self, username):
        user = self.old_apps.get_model("common", "User").objects.create(
            username=username
        )
        user.daily = self._model("Thread").objects.create(
            user=user,
            name="Daily",
            board_stream=self._stream(user, "board"),
            journal_stream=self._stream(user, "journal"),
        )
        return user

    def _habit(self, user, slug):
        return self._model("Habit").objects.create(
            user=user,
            name=slug.title(),
            slug=slug,
            event_stream=self._stream(user, "habit"),
        )

    def _tracked(self, habit, note):
        """A tracked habit, a member of its home stream, as Event.save left it
        (historical models don't run it)."""
        entry = self._model("HabitTracked").objects.create(
            habit=habit,
            note=note,
            thread=habit.user.daily,
            event_stream_id=habit.event_stream_id,
            created_by=habit.user,
        )
        self._model("EventStreamEntry").objects.create(
            event_id=entry.pk, stream_id=habit.event_stream_id
        )
        return entry

    def _note(self, apps, entry):
        return apps.get_model("tree", "HabitTracked").objects.get(pk=entry.pk).note

    def test_notes_get_their_metrics_as_tokens(self):
        alice = self._user("alice")
        health = self._habit(alice, "health")
        workout = self._habit(alice, "workout")
        til = self._habit(alice, "til")
        steps = self._tracked(health, "#health 7000 kroków")
        pressure = self._tracked(health, "#health 120/80")
        running = self._tracked(workout, "#running distance=3.0km, time=22m30s")
        synced = self._tracked(health, "steps=5000 distance=3.5km active=80min kcal=2")
        link = self._tracked(til, "#til https://example.com/watch?v=4dSLx2")
        plain = self._tracked(til, "#til nothing to count")

        apps = self._migrate()

        self.assertEqual(self._note(apps, steps), "#health 7000 kroków (steps=7000)")
        self.assertEqual(self._note(apps, pressure), "#health 120/80 (pressure=120/80)")
        self.assertEqual(
            self._note(apps, running), "#running distance=3.0km, duration=22m30s"
        )
        self.assertEqual(self._note(apps, synced), synced.note)
        self.assertEqual(self._note(apps, link), link.note)
        self.assertEqual(self._note(apps, plain), plain.note)

    def test_body_weight_under_health_moves_to_the_weight_habit(self):
        alice = self._user("alice")
        health = self._habit(alice, "health")
        weight = self._habit(alice, "weight")
        trip = self._stream(alice, "trip")
        entry = self._tracked(health, "#health 80.5kg")
        self._model("EventStreamEntry").objects.create(
            event_id=entry.pk, stream_id=trip.pk
        )
        steps = self._tracked(health, "#health 7000 kroków")

        apps = self._migrate()
        HabitTracked = apps.get_model("tree", "HabitTracked")
        EventStreamEntry = apps.get_model("tree", "EventStreamEntry")

        moved = HabitTracked.objects.get(pk=entry.pk)
        self.assertEqual(moved.habit_id, weight.pk)
        self.assertEqual(moved.note, "#health 80.5kg (weight=80.5kg)")
        self.assertEqual(moved.event_stream_id, weight.event_stream_id)
        self.assertEqual(
            set(
                EventStreamEntry.objects.filter(event_id=entry.pk).values_list(
                    "stream_id", flat=True
                )
            ),
            {weight.event_stream_id, trip.pk},
        )
        # What isn't body weight stays where it was.
        self.assertEqual(HabitTracked.objects.get(pk=steps.pk).habit_id, health.pk)

    def test_body_weight_stays_under_health_for_someone_without_a_weight_habit(self):
        bob = self._user("bob")
        health = self._habit(bob, "health")
        entry = self._tracked(health, "#health 80.5kg")

        apps = self._migrate()

        stayed = apps.get_model("tree", "HabitTracked").objects.get(pk=entry.pk)
        self.assertEqual(stayed.habit_id, health.pk)
        self.assertEqual(stayed.note, "#health 80.5kg (weight=80.5kg)")

    def test_a_fix_applies_to_the_entry_and_the_note_it_was_written_for(self):
        alice = self._user("alice")
        workout = self._habit(alice, "workout")
        conflict = "#siłka 3km biegu, 4km rowerem"
        fixed = self._tracked(workout, conflict)
        other = self._tracked(workout, conflict)
        changed = self._tracked(workout, "#siłka 60kg sztanga")

        with fixes(
            (fixed.pk, conflict, rules.append("distance=7km")),
            (changed.pk, conflict, rules.append("distance=7km")),
        ):
            apps = self._migrate()

        self.assertEqual(self._note(apps, fixed), f"{conflict} (distance=7km)")
        # Not the entry the fix is for: the conflict stays.
        self.assertEqual(self._note(apps, other), conflict)
        # The entry the fix is for, saying something else: read as it is.
        self.assertEqual(self._note(apps, changed), "#siłka 60kg sztanga (load=60kg)")

    def test_forward_backward_twice_puts_every_habit_back(self):
        alice = self._user("alice")
        health = self._habit(alice, "health")
        weight = self._habit(alice, "weight")
        workout = self._habit(alice, "workout")
        til = self._habit(alice, "til")
        trip = self._stream(alice, "trip")
        moved = self._tracked(health, "#health 80.5kg")
        self._model("EventStreamEntry").objects.create(
            event_id=moved.pk, stream_id=trip.pk
        )
        self._tracked(weight, "#weight weight=79kg")
        self._tracked(health, "#health 7000 kroków")
        self._tracked(health, "#health 120/80")
        self._tracked(workout, "#running distance=3.0km, time=22m30s")
        self._tracked(workout, "#workout Bike ride (duration=45 min)")
        self._tracked(health, "steps=5000 distance=3.5km active=80min kcal=2000")
        self._tracked(til, "#til nothing to count")
        conflict = "#siłka 3km biegu, 4km rowerem"
        fixed = self._tracked(workout, conflict)
        self._tracked(workout, conflict)
        before = self._habits()

        with fixes((fixed.pk, conflict, rules.append("distance=7km"))):
            self._migrate()
            forward = self._habits()
            self.assertNotEqual(forward, before)
            self.assertTrue(self._kept())

            self._migrate(BEFORE)
            self.assertEqual(self._habits(), before)
            self.assertFalse(self._kept())

            self._migrate()
            self.assertEqual(self._habits(), forward)

            self._migrate(BEFORE)
            self.assertEqual(self._habits(), before)
            self.assertFalse(self._kept())

    def test_backward_leaves_an_entry_changed_since(self):
        alice = self._user("alice")
        health = self._habit(alice, "health")
        weight = self._habit(alice, "weight")
        edited = self._tracked(health, "#health 7000 kroków")
        moved = self._tracked(health, "#health 80.5kg")

        apps = self._migrate()
        HabitTracked = apps.get_model("tree", "HabitTracked")
        HabitTracked.objects.filter(pk=edited.pk).update(note="#health 8000 kroków")
        HabitTracked.objects.filter(pk=moved.pk).update(habit_id=health.pk)

        apps = self._migrate(BEFORE)
        HabitTracked = apps.get_model("tree", "HabitTracked")

        self.assertEqual(
            HabitTracked.objects.get(pk=edited.pk).note, "#health 8000 kroków"
        )
        # Its note is put back; its habit, moved by hand since, is not.
        self.assertEqual(HabitTracked.objects.get(pk=moved.pk).note, "#health 80.5kg")
        self.assertNotEqual(HabitTracked.objects.get(pk=moved.pk).habit_id, weight.pk)
