from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from ...services.provisioning import provision_user


class Command(BaseCommand):
    help = (
        "Create the built-in threads, their boards and a profile for every user"
        " that is missing them. Safe to run repeatedly."
    )

    def handle(self, *args, **options):
        users = get_user_model().objects.order_by("pk")
        for user in users:
            provision_user(user)
        self.stdout.write(f"Provisioned {users.count()} user(s).")
