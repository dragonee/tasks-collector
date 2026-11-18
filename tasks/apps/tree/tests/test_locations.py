"""Where an event happened: EventLocation, sent by the phones as fields, or
read off an older phone's place line."""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import EventLocation, JournalAdded, Thread
from ..services.locations import Place, place_from, split_place

User = get_user_model()


class SplitPlaceTest(SimpleTestCase):
    def test_a_leading_place_line_is_read_off(self):
        self.assertEqual(
            split_place("#poi lat=40.7128 lng=-74.0060 acc=12.5\nat the pier"),
            ("at the pier", Place(40.7128, -74.006, 12.5)),
        )
        self.assertEqual(
            split_place("#coords lat=1 lng=2"), ("", Place(1.0, 2.0, None))
        )

    def test_a_place_line_elsewhere_or_off_the_earth_stays(self):
        for comment in (
            "at the pier\n#poi lat=1 lng=2",
            "Saw a #poi sign here",
            "#poi lat=91 lng=0\nnorth of north",
            "#poi 50.06,19.94",
        ):
            with self.subTest(comment=comment):
                self.assertEqual(split_place(comment), (comment, None))


class PlaceFromTest(SimpleTestCase):
    def test_fields_name_a_place(self):
        self.assertEqual(
            place_from({"lat": "52.1", "lng": 21, "acc": 5}), Place(52.1, 21.0, 5.0)
        )
        self.assertEqual(place_from({"lat": 52.1, "lng": 21}), Place(52.1, 21.0, None))

    def test_no_fields_no_place(self):
        self.assertIsNone(place_from({"comment": "x"}))

    def test_a_place_that_is_none_is_refused(self):
        for data in (
            {"lat": 52.1},
            {"lat": "north", "lng": 21},
            {"lat": 0, "lng": 181},
            {"lat": 0, "lng": 0, "acc": -1},
            {"lat": float("nan"), "lng": 0},
        ):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    place_from(data)


class PinTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice", password="x")
        cls.entry = JournalAdded.objects.create(
            thread=Thread.objects.daily(cls.user),
            comment="Miradouro",
            published=timezone.now(),
        )
        EventLocation.objects.create(event=cls.entry, lat=38.7139, lng=-9.1335)

    def test_an_entry_with_a_place_shows_its_pin(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("public-diary-archive-current-month"))
        self.assertContains(page, 'data-lat="38.7139" data-lng="-9.1335"')
        self.assertContains(page, "📍 38.71, -9.13")
