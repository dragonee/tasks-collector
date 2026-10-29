import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import BoardCommitted, Thread


def _at(day, hour):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))


class SummariesDateRangeTestCase(TestCase):
    """The summaries page filters committed boards by its From/To date
    inputs. Both days are inclusive, like the date pickers suggest."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        cls.url = reverse("summaries")

    def setUp(self):
        self.client.force_login(self.user)

    def _commit(self, published):
        return BoardCommitted.objects.create(
            thread=self.daily, published=published, focus=""
        )

    def _shown(self, params=None):
        response = self.client.get(self.url, params or {})
        self.assertEqual(response.status_code, 200)
        return [board.pk for board in response.context["boards"]]

    def test_to_day_is_included(self):
        day = datetime.date(2026, 10, 28)
        on_to_day = self._commit(_at(day, 15))
        self._commit(_at(day + datetime.timedelta(days=1), 9))

        self.assertEqual(
            self._shown({"from": "2026-10-27", "to": "2026-10-28"}), [on_to_day.pk]
        )

    def test_malformed_dates_fall_back_to_the_default_range(self):
        today = self._commit(timezone.now())

        self.assertEqual(self._shown({"from": "foo", "to": "bar"}), [today.pk])

    def test_default_range_includes_today(self):
        today = self._commit(timezone.now())
        self._commit(timezone.now() - datetime.timedelta(days=40))

        self.assertEqual(self._shown(), [today.pk])
