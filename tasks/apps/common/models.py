import datetime
import hashlib
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.utils import timezone


class User(AbstractUser):
    pass


def _digest(secret):
    """What is kept of a token or a code. They are long and random, so a
    plain hash is enough to keep a copy of the database from being a list of
    working credentials."""
    return hashlib.sha256(secret.encode()).hexdigest()


class ApiTokenManager(models.Manager):
    def issue(self, user, name):
        """A new token of ``user``'s: (the row, its key). The key exists
        here and with whoever is handed it; it can't be read back."""
        key = secrets.token_urlsafe(32)
        return self.create(user=user, name=name, digest=_digest(key)), key

    def for_key(self, key):
        """The token with this key, or None."""
        return self.select_related("user").filter(digest=_digest(key)).first()


class ApiToken(models.Model):
    """What a client sends as ``Authorization: Token <key>``.

    A user has one for each device or script that is logged in as them: the
    phone gets its own by logging in (``oauth.py``), a script from
    ``manage.py issue_mobile_token``. Deleting the row revokes it.
    """

    # How stale ``last_used`` may get: one write per token per hour, not one
    # per request.
    USED_RESOLUTION = datetime.timedelta(hours=1)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens"
    )
    # What the user knows it by: "Tasks Health on Pixel 8".
    name = models.CharField(max_length=150)
    digest = models.CharField(max_length=64, unique=True, editable=False)
    created = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True, editable=False)

    objects = ApiTokenManager()

    class Meta:
        ordering = ("-created",)

    def __str__(self):
        return self.name

    def used(self):
        """Note that the token was used just now."""
        now = timezone.now()
        if self.last_used is None or now - self.last_used > self.USED_RESOLUTION:
            self.last_used = now
            type(self).objects.filter(pk=self.pk).update(last_used=now)


class AuthorizationCodeManager(models.Manager):
    def issue(self, user, client_id, redirect_uri, code_challenge, device_name):
        """A code for what ``user`` just allowed. Returns the code itself."""
        self.filter(created__lt=timezone.now() - AuthorizationCode.LIFETIME).delete()
        code = secrets.token_urlsafe(32)
        self.create(
            digest=_digest(code),
            user=user,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            device_name=device_name,
        )
        return code

    def redeem(self, code):
        """The authorization ``code`` stands for, or None when there is none
        or it is too old. Either way the code is used up."""
        with transaction.atomic():
            row = self.select_for_update().filter(digest=_digest(code)).first()
            if row is None:
                return None
            row.delete()
        if row.created < timezone.now() - AuthorizationCode.LIFETIME:
            return None
        return row


class AuthorizationCode(models.Model):
    """A user's "yes" to a client that asked for a token, on its way to that
    client (OAuth 2.0 authorization code, see ``oauth.py``): good once, and
    for a few minutes."""

    LIFETIME = datetime.timedelta(minutes=5)

    digest = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # What the client said when it asked; it has to say the same again, and
    # show the verifier of the challenge, to get the token.
    client_id = models.CharField(max_length=100)
    redirect_uri = models.CharField(max_length=500)
    code_challenge = models.CharField(max_length=128)
    device_name = models.CharField(max_length=100, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    objects = AuthorizationCodeManager()
