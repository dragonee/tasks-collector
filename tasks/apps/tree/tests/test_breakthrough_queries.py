from datetime import date

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..models import Breakthrough, ProjectedOutcome, ProjectedOutcomeEvolved, Thread


class BreakthroughPageQueriesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        Thread.objects.create(name="Daily")
        cls.breakthrough = Breakthrough.objects.create(slug="2026")

    def setUp(self):
        self.client.force_login(self.user)

    def add_outcome_with_note(self, n):
        outcome = ProjectedOutcome.objects.create(
            breakthrough=self.breakthrough,
            name=f"Outcome {n}",
            description="",
            resolved_by=date(2026, 6, n),
        )
        ProjectedOutcomeEvolved.from_projected_outcome(outcome, f"Note {n}").save()

    def count_page_queries(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("breakthrough", args=[2026]))
        self.assertEqual(response.status_code, 200)
        return response, len(queries)

    def test_evolved_notes_do_not_add_a_query_per_outcome(self):
        self.add_outcome_with_note(1)
        # Warm up per-process caches (e.g. polymorphic content types).
        self.count_page_queries()
        _, one_outcome = self.count_page_queries()

        self.add_outcome_with_note(2)
        self.add_outcome_with_note(3)
        response, three_outcomes = self.count_page_queries()

        self.assertEqual(three_outcomes, one_outcome)
        for n in (1, 2, 3):
            self.assertContains(response, f"Note {n}")
