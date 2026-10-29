from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import (
    Breakthrough,
    Event,
    ProjectedOutcome,
    ProjectedOutcomeClosed,
    ProjectedOutcomeEvolved,
    ProjectedOutcomeMade,
    ProjectedOutcomeMoved,
    Thread,
)
from ..services.breakthrough.operations import (
    close_projected_outcome,
    evolve_projected_outcome,
    move_projected_outcome_to_next_year,
)


class ProjectedOutcomeTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        Thread.objects.create(name="Daily")
        cls.breakthrough = Breakthrough.objects.create(slug="2026")

    def create_outcome(self, **kwargs):
        return ProjectedOutcome.objects.create(
            **{
                "breakthrough": self.breakthrough,
                "name": "Sleep 8h",
                "description": "Every night",
                "resolved_by": date(2026, 6, 30),
                **kwargs,
            }
        )

    def stream_types(self, outcome):
        return [
            type(e)
            for e in Event.objects.filter(event_stream_id=outcome.event_stream_id)
        ]


class CloseProjectedOutcomeTestCase(ProjectedOutcomeTestMixin, TestCase):
    def test_records_final_state_and_deletes_outcome(self):
        outcome = self.create_outcome()

        closed = close_projected_outcome(outcome)

        self.assertFalse(ProjectedOutcome.objects.filter(name="Sleep 8h").exists())
        closed.refresh_from_db()
        self.assertEqual(closed.name, "Sleep 8h")
        self.assertEqual(closed.breakthrough, self.breakthrough)
        self.assertEqual(closed.event_stream_id, outcome.event_stream_id)
        self.assertEqual(
            self.stream_types(outcome), [ProjectedOutcomeMade, ProjectedOutcomeClosed]
        )

    def test_keeps_outcome_when_delete_fails(self):
        outcome = self.create_outcome()

        with mock.patch.object(
            ProjectedOutcome, "delete", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                close_projected_outcome(outcome)

        self.assertTrue(ProjectedOutcome.objects.filter(pk=outcome.pk).exists())
        self.assertFalse(ProjectedOutcomeClosed.objects.exists())


class MoveProjectedOutcomeTestCase(ProjectedOutcomeTestMixin, TestCase):
    def test_moves_to_a_new_next_year_breakthrough(self):
        outcome = self.create_outcome(confidence_level=40)

        new_breakthrough = move_projected_outcome_to_next_year(outcome)

        self.assertEqual(new_breakthrough.slug, "2027")
        outcome.refresh_from_db()
        self.assertEqual(outcome.breakthrough, new_breakthrough)
        moved = ProjectedOutcomeMoved.objects.get()
        self.assertEqual(moved.old_breakthrough, self.breakthrough)
        self.assertEqual(moved.new_breakthrough, new_breakthrough)
        self.assertEqual(moved.confidence_level, 40)
        self.assertEqual(moved.event_stream_id, outcome.event_stream_id)

    def test_reuses_existing_next_year_breakthrough(self):
        existing = Breakthrough.objects.create(slug="2027", theme="Next")
        outcome = self.create_outcome()

        self.assertEqual(move_projected_outcome_to_next_year(outcome), existing)
        self.assertEqual(Breakthrough.objects.filter(slug="2027").count(), 1)

    def test_does_not_leave_next_year_breakthrough_when_event_fails(self):
        outcome = self.create_outcome()

        with mock.patch.object(
            ProjectedOutcomeMoved, "save", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                move_projected_outcome_to_next_year(outcome)

        self.assertFalse(Breakthrough.objects.filter(slug="2027").exists())
        outcome.refresh_from_db()
        self.assertEqual(outcome.breakthrough, self.breakthrough)


class EvolveProjectedOutcomeTestCase(ProjectedOutcomeTestMixin, TestCase):
    def test_adds_note_to_outcome_stream(self):
        outcome = self.create_outcome()

        evolved = evolve_projected_outcome(outcome, "Halfway there")

        evolved.refresh_from_db()
        self.assertEqual(evolved.note, "Halfway there")
        self.assertEqual(evolved.projected_outcome, outcome)
        self.assertEqual(evolved.event_stream_id, outcome.event_stream_id)


class ProjectedOutcomeEndpointsTestCase(ProjectedOutcomeTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)

    def test_close(self):
        outcome = self.create_outcome()
        url = reverse("projected-outcome-close", args=[outcome.pk])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["HX-Redirect"], reverse("breakthrough", args=["2026"])
        )
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_close_requires_post(self):
        outcome = self.create_outcome()

        response = self.client.get(
            reverse("projected-outcome-close", args=[outcome.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(ProjectedOutcome.objects.filter(pk=outcome.pk).exists())

    def test_close_requires_authentication(self):
        outcome = self.create_outcome()
        self.client.logout()

        response = self.client.post(
            reverse("projected-outcome-close", args=[outcome.pk])
        )

        self.assertEqual(response.status_code, 401)
        self.assertTrue(ProjectedOutcome.objects.filter(pk=outcome.pk).exists())

    def test_move(self):
        outcome = self.create_outcome()

        response = self.client.post(
            reverse("projected-outcome-move", args=[outcome.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["HX-Redirect"], reverse("breakthrough", args=["2026"])
        )
        outcome.refresh_from_db()
        self.assertEqual(outcome.breakthrough.slug, "2027")

    def test_evolve(self):
        outcome = self.create_outcome()
        url = reverse("projected-outcome-evolve", args=[outcome.pk])

        response = self.client.post(url, {"note": "Halfway there"})

        self.assertContains(response, "Halfway there")
        self.assertEqual(self.client.post(url, {"note": ""}).status_code, 400)
        self.assertEqual(ProjectedOutcomeEvolved.objects.count(), 1)

    def test_evolve_closed_outcome_is_404(self):
        outcome = self.create_outcome()
        pk = outcome.pk
        close_projected_outcome(outcome)

        response = self.client.post(
            reverse("projected-outcome-evolve", args=[pk]), {"note": "Too late"}
        )

        self.assertEqual(response.status_code, 404)
