"""The settings: a page for each section under a second-level menu, each
saving only what it shows."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import HabitKeyword, Profile, Thread
from ..views_settings import MENU
from .factories import make_habit, make_profile, make_thread

SECTIONS = [section for _, sections in MENU for section in sections]


class SettingsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="me", password="x")
        cls.other = User.objects.create_user(username="other", password="x")
        cls.errands = make_thread(cls.user, "Errands")
        make_habit(cls.user, "Running", keywords=["run", "jog"])
        make_habit(cls.other, "Reading", keywords=["read"])
        cls.run_keyword = HabitKeyword.objects.get(keyword="run")
        cls.jog_keyword = HabitKeyword.objects.get(keyword="jog")

    def setUp(self):
        self.client.force_login(self.user)

    def _profile(self):
        return Profile.objects.get(user=self.user)

    def test_settings_open_on_the_first_section(self):
        response = self.client.get(reverse("account-settings"))

        self.assertRedirects(response, reverse("settings-profile"))

    def test_every_section_has_a_titled_page_under_the_menu(self):
        for section in SECTIONS:
            with self.subTest(section=section.title):
                page = self.client.get(reverse(section.url_name))

                self.assertContains(page, f"<h1>{section.title}</h1>", html=True)
                self.assertContains(page, section.description)
                self.assertContains(page, 'aria-current="page"', count=1)
                for group, sections in MENU:
                    self.assertContains(page, f"<h2>{group}</h2>", html=True)
                    for other in sections:
                        self.assertContains(page, reverse(other.url_name))

    def test_the_settings_are_for_someone_logged_in(self):
        self.client.logout()

        for name in ["account-settings"] + [s.url_name for s in SECTIONS]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))

                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response["Location"])

    def test_the_profile_saves_the_name(self):
        response = self.client.post(
            reverse("settings-profile"),
            {"first_name": "Ada", "last_name": "Byron"},
            follow=True,
        )

        self.assertRedirects(response, reverse("settings-profile"))
        self.assertContains(response, "Profile saved.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_full_name(), "Ada Byron")

    def test_a_section_saves_only_what_it_shows(self):
        make_profile(self.user, default_board_thread=self.errands, map_provider="osm")
        self._profile().habit_keywords.set([self.run_keyword])

        self.client.post(reverse("settings-maps"), {"map_provider": "google"})
        self.client.post(reverse("settings-profile"), {"first_name": "Ada"})

        profile = self._profile()
        self.assertEqual(profile.map_provider, "google")
        self.assertEqual(profile.default_board_thread, self.errands)
        self.assertEqual(list(profile.habit_keywords.all()), [self.run_keyword])

    def test_boards_save_the_default_board(self):
        response = self.client.post(
            reverse("settings-boards"), {"default_board_thread": self.errands.pk}
        )

        self.assertRedirects(response, reverse("settings-boards"))
        self.assertEqual(self._profile().default_board_thread, self.errands)

    def test_boards_refuse_someone_elses_board(self):
        theirs = Thread.objects.daily(self.other)

        response = self.client.post(
            reverse("settings-boards"), {"default_board_thread": theirs.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "errorlist")
        self.assertIsNone(self._profile().default_board_thread)

    def test_habits_offer_my_keywords_and_save_the_ticked_ones(self):
        page = self.client.get(reverse("settings-habits"))

        self.assertContains(page, "Running: run")
        self.assertNotContains(page, "Reading")

        self.client.post(
            reverse("settings-habits"), {"habit_keywords": [self.jog_keyword.pk]}
        )

        self.assertEqual(list(self._profile().habit_keywords.all()), [self.jog_keyword])

    def test_habits_can_be_left_with_no_keyword_ticked(self):
        self._profile().habit_keywords.set([self.run_keyword])

        response = self.client.post(reverse("settings-habits"), {})

        self.assertRedirects(response, reverse("settings-habits"))
        self.assertFalse(self._profile().habit_keywords.exists())
