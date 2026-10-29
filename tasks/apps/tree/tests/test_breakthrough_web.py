from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Breakthrough

FORMSET_PREFIX = "projectedoutcome_set"


def breakthrough_post_data(**overrides):
    data = {
        "areas_of_concern": "Sleep",
        "theme": "Rest",
        f"{FORMSET_PREFIX}-TOTAL_FORMS": "0",
        f"{FORMSET_PREFIX}-INITIAL_FORMS": "0",
        f"{FORMSET_PREFIX}-MIN_NUM_FORMS": "0",
        f"{FORMSET_PREFIX}-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


class BreakthroughReviewModeTestCase(TestCase):
    """Review mode is the default, so leaving it (``?review=0``) has to be
    carried explicitly through every link and redirect, or the page silently
    drops back into review mode."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="u", password="x")
        Breakthrough.objects.create(slug="2026")

    def setUp(self):
        self.client.force_login(self.user)

    def url(self, year, review):
        return f"{reverse('breakthrough', args=[year])}?review={review}"

    def test_save_outside_review_mode_stays_outside_review_mode(self):
        response = self.client.post(self.url(2026, "0"), breakthrough_post_data())

        self.assertRedirects(
            response, self.url(2026, "0"), fetch_redirect_response=False
        )
        self.assertEqual(Breakthrough.objects.get(slug="2026").theme, "Rest")

    def test_save_in_review_mode_stays_in_review_mode(self):
        response = self.client.post(self.url(2026, "1"), breakthrough_post_data())

        self.assertRedirects(
            response, self.url(2026, "1"), fetch_redirect_response=False
        )

    def test_year_navigation_keeps_review_mode_off(self):
        response = self.client.get(self.url(2026, "0"))

        self.assertContains(response, f'href="{self.url(2025, "0")}"')
        self.assertContains(response, f'href="{self.url(2027, "0")}"')

    def test_year_navigation_keeps_review_mode_on(self):
        response = self.client.get(reverse("breakthrough", args=[2026]))

        self.assertContains(response, f'href="{self.url(2025, "1")}"')
        self.assertContains(response, f'href="{self.url(2027, "1")}"')
