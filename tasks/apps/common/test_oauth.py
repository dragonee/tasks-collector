"""Logging a device in (oauth.py) and the tokens that come of it."""

import base64
import datetime
import hashlib
import io
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import ApiToken, AuthorizationCode

REDIRECT_URI = "org.polybrain.tasks.health:/oauth"
VERIFIER = "v" * 43
AGENDA = "/api/v1/tasks/agenda/?date=2026-11-11"


def challenge_of(verifier):
    hashed = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(hashed).rstrip(b"=").decode()


def authorize_url(**changed):
    asked = {
        "response_type": "code",
        "client_id": "tasks-android",
        "redirect_uri": REDIRECT_URI,
        "code_challenge": challenge_of(VERIFIER),
        "code_challenge_method": "S256",
        "state": "xyz",
        "device_name": "Pixel 8",
    }
    asked.update(changed)
    return reverse("oauth-authorize") + "?" + urlencode(asked)


def answer(response):
    """Where the browser is sent back to, and what it carries."""
    sent_to = urlsplit(response["Location"])
    said = {key: values[0] for key, values in parse_qs(sent_to.query).items()}
    return f"{sent_to.scheme}:{sent_to.path}", said


class OAuthTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="alice", password="pw")
        cls.other = User.objects.create_user(username="bob", password="pw")

    def setUp(self):
        self.client.force_login(self.user)

    def _code(self, **changed):
        response = self.client.post(authorize_url(**changed), {"allow": "1"})
        self.assertEqual(response.status_code, 302)
        return answer(response)[1]["code"]

    def _trade(self, code, **changed):
        sent = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": VERIFIER,
            "client_id": "tasks-android",
            "redirect_uri": REDIRECT_URI,
        }
        sent.update(changed)
        # As the app does it: no session, no CSRF token.
        return Client(enforce_csrf_checks=True).post(reverse("oauth-token"), sent)

    def _key(self):
        return self._trade(self._code()).json()["access_token"]

    def _agenda_with(self, key):
        return Client().get(AGENDA, HTTP_AUTHORIZATION=f"Token {key}")


class LogInTestCase(OAuthTestCase):
    def test_the_password_is_asked_for_first(self):
        url = authorize_url()

        response = Client().get(url)

        self.assertEqual(response.status_code, 302)
        login = urlsplit(response["Location"])
        self.assertEqual(login.path, "/accounts/login/")
        # ...and then it goes on where it was.
        self.assertEqual(parse_qs(login.query)["next"], [url])

    def test_a_device_gets_a_token_of_its_own(self):
        page = self.client.get(authorize_url())
        self.assertContains(page, "Log Tasks Health on Pixel 8 in?")
        self.assertContains(page, "alice")
        self.assertFalse(AuthorizationCode.objects.exists())

        allowed = self.client.post(authorize_url(), {"allow": "1"})

        self.assertEqual(allowed.status_code, 302)
        sent_to, said = answer(allowed)
        self.assertEqual(sent_to, REDIRECT_URI)
        self.assertEqual(said["state"], "xyz")

        traded = self._trade(said["code"])

        self.assertEqual(traded.status_code, 200, traded.content)
        self.assertEqual(traded["Cache-Control"], "no-store")
        self.assertEqual(traded.json()["token_type"], "Token")
        key = traded.json()["access_token"]
        token = ApiToken.objects.get()
        self.assertEqual(
            (token.user, token.name), (self.user, "Tasks Health on Pixel 8")
        )
        # Neither the key nor the code is kept.
        self.assertNotIn(key, (token.digest, token.name))
        self.assertFalse(AuthorizationCode.objects.exists())

        self.assertEqual(self._agenda_with(key).status_code, 200)

    def test_a_debug_build_is_sent_back_to_itself(self):
        debug = "org.polybrain.tasks.health.debug:/oauth"

        code = self._code(redirect_uri=debug, device_name="")

        self.assertEqual(self._trade(code, redirect_uri=debug).status_code, 200)
        self.assertEqual(ApiToken.objects.get().name, "Tasks Health")

    def test_saying_no_gives_no_code(self):
        response = self.client.post(authorize_url(), {"deny": "1"})

        sent_to, said = answer(response)
        self.assertEqual(sent_to, REDIRECT_URI)
        self.assertEqual(said, {"error": "access_denied", "state": "xyz"})
        self.assertFalse(AuthorizationCode.objects.exists())

    def test_the_yes_has_to_come_from_the_page(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)

        response = browser.post(authorize_url(), {"allow": "1"})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AuthorizationCode.objects.exists())

    def test_an_answer_is_only_sent_where_the_app_is_known_to_be(self):
        for changed in (
            {"client_id": "someone-else"},
            {"redirect_uri": "https://evil.example/oauth"},
            {"redirect_uri": REDIRECT_URI + "/elsewhere"},
            {"redirect_uri": ""},
        ):
            with self.subTest(changed):
                for response in (
                    self.client.get(authorize_url(**changed)),
                    self.client.post(authorize_url(**changed), {"allow": "1"}),
                ):
                    self.assertEqual(response.status_code, 400)
                    self.assertNotIn("Location", response)
                    self.assertContains(response, "doesn't work", status_code=400)
        self.assertFalse(AuthorizationCode.objects.exists())

    def test_a_request_without_pkce_is_refused(self):
        for changed, error in (
            ({"code_challenge": ""}, "invalid_request"),
            ({"code_challenge_method": "plain"}, "invalid_request"),
            ({"code_challenge": "short"}, "invalid_request"),
            ({"response_type": "token"}, "unsupported_response_type"),
        ):
            with self.subTest(changed):
                response = self.client.post(authorize_url(**changed), {"allow": "1"})

                self.assertEqual(answer(response)[1]["error"], error)
        self.assertFalse(AuthorizationCode.objects.exists())


class TradeTestCase(OAuthTestCase):
    def _refused(self, response, error="invalid_grant"):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": error})
        self.assertFalse(ApiToken.objects.exists())

    def test_a_code_is_good_once(self):
        code = self._code()
        self.assertEqual(self._trade(code).status_code, 200)

        again = self._trade(code)

        self.assertEqual(again.status_code, 400)
        self.assertEqual(ApiToken.objects.count(), 1)

    def test_only_the_app_that_asked_can_use_it(self):
        # It knows the verifier of the challenge it sent; one try.
        code = self._code()

        self._refused(self._trade(code, code_verifier="w" * 43))
        self._refused(self._trade(code))

    def test_what_was_asked_has_to_be_said_again(self):
        for changed in (
            {"client_id": "someone-else"},
            {"redirect_uri": "org.polybrain.tasks.health.debug:/oauth"},
            {"code_verifier": ""},
        ):
            with self.subTest(changed):
                self._refused(self._trade(self._code(), **changed))

    def test_a_made_up_code_is_refused(self):
        self._code()

        self._refused(self._trade("made-up"))
        self._refused(self._trade(""))

    def test_a_code_is_good_for_a_few_minutes(self):
        code = self._code()
        AuthorizationCode.objects.update(
            created=timezone.now() - AuthorizationCode.LIFETIME - datetime.timedelta(1)
        )

        self._refused(self._trade(code))

    def test_old_codes_are_cleared_away(self):
        self._code()
        AuthorizationCode.objects.update(
            created=timezone.now() - datetime.timedelta(hours=1)
        )

        self._code()

        self.assertEqual(AuthorizationCode.objects.count(), 1)

    def test_only_codes_are_traded(self):
        self._refused(
            self._trade(self._code(), grant_type="password"), "unsupported_grant_type"
        )

    def test_a_user_who_was_locked_out_meanwhile_gets_nothing(self):
        code = self._code()
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)

        self._refused(self._trade(code))


class TokenTestCase(OAuthTestCase):
    def test_a_wrong_token_is_nobody(self):
        self._key()

        for key in ("made-up", ""):
            with self.subTest(key):
                self.assertEqual(self._agenda_with(key).status_code, 401)

    def test_the_token_of_a_locked_out_user_is_nobody(self):
        key = self._key()
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)

        self.assertEqual(self._agenda_with(key).status_code, 401)

    def test_when_it_was_last_used_is_noted_now_and_then(self):
        key = self._key()
        self.assertIsNone(ApiToken.objects.get().last_used)

        self._agenda_with(key)
        first = ApiToken.objects.get().last_used
        self.assertIsNotNone(first)

        # Not a write with every request.
        self._agenda_with(key)
        self.assertEqual(ApiToken.objects.get().last_used, first)

        ApiToken.objects.update(last_used=first - datetime.timedelta(hours=2))
        self._agenda_with(key)
        self.assertGreaterEqual(ApiToken.objects.get().last_used, first)

    def test_the_app_logs_itself_out(self):
        key = self._key()
        mine = self._key()

        for _ in range(2):
            response = Client(enforce_csrf_checks=True).post(
                reverse("oauth-revoke"), {"token": key}
            )
            self.assertEqual(response.status_code, 200)

        self.assertEqual(self._agenda_with(key).status_code, 401)
        self.assertEqual(self._agenda_with(mine).status_code, 200)

    def test_the_settings_list_the_devices_and_log_one_out(self):
        key = self._key()
        token = ApiToken.objects.get()

        page = self.client.get(reverse("settings-devices"))
        self.assertContains(page, "Tasks Health on Pixel 8")
        self.assertContains(page, reverse("api-token-revoke", args=[token.pk]))

        response = self.client.post(reverse("api-token-revoke", args=[token.pk]))

        self.assertRedirects(response, reverse("settings-devices"))
        self.assertFalse(ApiToken.objects.exists())
        self.assertEqual(self._agenda_with(key).status_code, 401)
        self.assertContains(
            self.client.get(reverse("settings-devices")), "Nothing is logged in."
        )

    def test_nobody_logs_out_someone_elses_device(self):
        key = self._key()
        token = ApiToken.objects.get()
        theirs = Client()
        theirs.force_login(self.other)

        page = theirs.get(reverse("settings-devices"))
        response = theirs.post(reverse("api-token-revoke", args=[token.pk]))
        anonymous = Client().post(reverse("api-token-revoke", args=[token.pk]))

        self.assertNotContains(page, "Pixel 8")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(anonymous.status_code, 302)
        self.assertEqual(self._agenda_with(key).status_code, 200)

    def test_the_command_issues_a_token_for_a_script(self):
        out = io.StringIO()
        call_command("issue_mobile_token", "alice", stdout=out)
        first = out.getvalue().strip()

        self.assertEqual(self._agenda_with(first).status_code, 200)
        self.assertEqual(ApiToken.objects.get().name, "issue_mobile_token")

        out = io.StringIO()
        call_command("issue_mobile_token", "alice", "--rotate", stdout=out)
        second = out.getvalue().strip()

        self.assertEqual(self._agenda_with(first).status_code, 401)
        self.assertEqual(self._agenda_with(second).status_code, 200)
        self.assertEqual(ApiToken.objects.count(), 1)


class CarryOverTestCase(TransactionTestCase):
    """0003: the tokens ``rest_framework.authtoken`` issued keep working."""

    BEFORE = [("common", "0002_alter_user_first_name")]
    AFTER = [("common", "0003_api_tokens")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.BEFORE)
        self.old_apps = executor.loader.project_state(self.BEFORE).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.AFTER)

    def test_a_token_from_before_still_logs_its_user_in(self):
        user = self.old_apps.get_model("common", "User").objects.create(username="u")
        issued = datetime.datetime(2026, 5, 1, 12, tzinfo=datetime.timezone.utc)
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE authtoken_token (
                    key varchar(40) PRIMARY KEY,
                    created timestamp with time zone NOT NULL,
                    user_id integer NOT NULL UNIQUE REFERENCES common_user (id)
                        DEFERRABLE INITIALLY DEFERRED
                )
                """)
            cursor.execute(
                "INSERT INTO authtoken_token (key, created, user_id) VALUES (%s, %s, %s)",
                ["0123456789abcdef0123456789abcdef01234567", issued, user.pk],
            )
            cursor.execute(
                "INSERT INTO django_migrations (app, name, applied)"
                " VALUES ('authtoken', '0001_initial', now())"
            )

        self._migrate()

        token = ApiToken.objects.for_key("0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(token.user_id, user.pk)
        self.assertEqual(token.created, issued)
        self.assertEqual(token.name, "Token issued before devices logged in")
        # The keys themselves are gone, and the app that kept them.
        self.assertNotIn("authtoken_token", connection.introspection.table_names())
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM django_migrations WHERE app = 'authtoken'"
            )
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_a_database_that_never_had_such_tokens(self):
        self._migrate()

        self.assertFalse(ApiToken.objects.exists())
