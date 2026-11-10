from django.core.management.base import BaseCommand

from ...services.streams import ensure_home_entries


class Command(BaseCommand):
    help = (
        "Make every event a member of its home stream. Safe to run any time; "
        "run it after deploying a release that adds stream entries."
    )

    def handle(self, *args, **options):
        added = ensure_home_entries()
        self.stdout.write(
            f"Added {added} missing home stream entr{'y' if added == 1 else 'ies'}."
        )
