from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from tasks.apps.common.models import ApiToken


class Command(BaseCommand):
    help = (
        "Issue an API token for a user and print it. For a script or a debug"
        " build of the phone app; a phone logs in by itself (Settings, Log in)."
        " The token is listed in the user's account settings under its name."
    )

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username to issue a token for")
        parser.add_argument(
            "--name",
            default="issue_mobile_token",
            help="What the token is listed as [default: issue_mobile_token]",
        )
        parser.add_argument(
            "--rotate",
            action="store_true",
            help="Revoke the user's tokens of that name first",
        )
        parser.add_argument(
            "--read-only",
            action="store_true",
            help="A token that can only read: what would change something is refused",
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
            ApiToken.objects.filter(user=user, name=options["name"]).delete()

        _token, key = ApiToken.objects.issue(
            user, options["name"], read_only=options["read_only"]
        )
        self.stdout.write(key)
