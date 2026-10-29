from datetime import date, datetime, timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Breakthrough, ProjectedOutcome, Thread


class ProjectedOutcomeHistoryBackLinkTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        Thread.objects.create(name="Daily")

    def setUp(self):
        self.client.force_login(self.user)

    def test_back_link_points_at_the_breakthrough_year(self):
        # Planned in December, or created by moving an outcome to next year:
        # the row's published year is not the year it is about.
        breakthrough = Breakthrough.objects.create(
            slug="2027", published=datetime(2026, 12, 20, tzinfo=timezone.utc)
        )
        outcome = ProjectedOutcome.objects.create(
            breakthrough=breakthrough,
            name="Sleep 8h",
            description="",
            resolved_by=date(2027, 6, 30),
        )

        response = self.client.get(
            reverse(
                "projected-outcome-events-history",
                kwargs={"event_stream_id": outcome.event_stream_id},
            )
        )

        self.assertContains(
            response,
            f'class="back-chevron" href="{reverse("breakthrough", args=[2027])}"',
        )
