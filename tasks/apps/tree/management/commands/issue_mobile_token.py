from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = (
        "Create or rotate a DRF auth token for a user. Prints the token value."
        " Intended for provisioning mobile clients."
    )

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username to issue a token for")
        parser.add_argument(
            "--rotate",
            action="store_true",
            help="Delete any existing token and create a fresh one",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError(
                f"No user found with username={options['username']!r}"
            ) from exc

        if options["rotate"]:
            Token.objects.filter(user=user).delete()

        token, _created = Token.objects.get_or_create(user=user)
        self.stdout.write(token.key)
