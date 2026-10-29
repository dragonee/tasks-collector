from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Breakthrough, ProjectedOutcome, ProjectedOutcomeMade, Thread

FORMSET_PREFIX = "projectedoutcome_set"


class BreakthroughNewYearTestCase(TestCase):
    """A year without a Breakthrough row yet (e.g. the sidebar link on
    January 1st) is rendered from an unsaved Breakthrough. Filtering
    outcomes by an unsaved instance raises ValueError on Django 5."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        Thread.objects.create(name="Daily")

    def setUp(self):
        self.client.force_login(self.user)

    def test_get_year_without_breakthrough(self):
        response = self.client.get(reverse("breakthrough", args=[2031]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Breakthrough.objects.filter(slug="2031").exists())

    def test_post_creates_breakthrough_with_first_outcome(self):
        response = self.client.post(
            reverse("breakthrough", args=[2031]),
            {
                "areas_of_concern": "Sleep",
                "theme": "Rest",
                f"{FORMSET_PREFIX}-TOTAL_FORMS": "1",
                f"{FORMSET_PREFIX}-INITIAL_FORMS": "0",
                f"{FORMSET_PREFIX}-MIN_NUM_FORMS": "0",
                f"{FORMSET_PREFIX}-MAX_NUM_FORMS": "1000",
                f"{FORMSET_PREFIX}-0-name": "Sleep 8h",
                f"{FORMSET_PREFIX}-0-resolved_by": "2031-06-30",
                f"{FORMSET_PREFIX}-0-description": "Every night",
                f"{FORMSET_PREFIX}-0-success_criteria": "",
                f"{FORMSET_PREFIX}-0-confidence_level": "20",
            },
        )

        self.assertEqual(response.status_code, 302)
        outcome = ProjectedOutcome.objects.get(name="Sleep 8h")
        self.assertEqual(outcome.breakthrough.slug, "2031")
        self.assertTrue(
            ProjectedOutcomeMade.objects.filter(
                event_stream_id=outcome.event_stream_id
            ).exists()
        )

    def test_year_lists_only_its_own_outcomes(self):
        for slug in ("2030", "2031"):
            ProjectedOutcome.objects.create(
                breakthrough=Breakthrough.objects.create(slug=slug),
                name=f"Outcome {slug}",
                description="",
                resolved_by=date(int(slug), 6, 30),
            )

        response = self.client.get(reverse("breakthrough", args=[2031]))

        self.assertContains(response, "Outcome 2031")
        self.assertNotContains(response, "Outcome 2030")
