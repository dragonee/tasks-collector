import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Breakthrough, ProjectedOutcome, ProjectedOutcomeClosed, Thread


class ProjectedOutcomeEventsHistoryNotFoundTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        Thread.objects.create(name="Daily")
        cls.breakthrough = Breakthrough.objects.create(slug="2026")

    def setUp(self):
        self.client.force_login(self.user)

    def history_url(self, event_stream_id):
        return reverse(
            "projected-outcome-events-history",
            kwargs={"event_stream_id": event_stream_id},
        )

    def create_outcome(self):
        return ProjectedOutcome.objects.create(
            breakthrough=self.breakthrough,
            name="Sleep 8h",
            description="",
            resolved_by=date(2026, 6, 30),
        )

    def test_unknown_event_stream_is_404(self):
        response = self.client.get(self.history_url(uuid.uuid4()))

        self.assertEqual(response.status_code, 404)

    def test_malformed_event_stream_is_404(self):
        response = self.client.get("/projected-outcome/abc-123/events/")

        self.assertEqual(response.status_code, 404)

    def test_active_outcome_history(self):
        outcome = self.create_outcome()

        response = self.client.get(self.history_url(outcome.event_stream_id))

        self.assertContains(response, "Sleep 8h")

    def test_closed_outcome_history(self):
        outcome = self.create_outcome()
        ProjectedOutcomeClosed.from_projected_outcome(outcome).save()
        outcome.delete()

        response = self.client.get(self.history_url(outcome.event_stream_id))

        self.assertContains(response, "Sleep 8h (Closed)")


class BreakthroughYearOutOfRangeTestCase(TestCase):
    """Year 0 used to 500 on reversing the year - 1 link. Years past 9999 (or
    a last_year of 0) made the timeline query raise, which the template's
    ``{% if %}`` silently swallowed into an empty page."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")

    def setUp(self):
        self.client.force_login(self.user)

    def test_years_outside_datetime_range_are_404(self):
        for year in (0, 1, 9999, 10000):
            Breakthrough.objects.create(slug=str(year))
            with self.subTest(year=year):
                response = self.client.get(reverse("breakthrough", args=[year]))

                self.assertEqual(response.status_code, 404)
