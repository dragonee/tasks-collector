from django.core.management.base import BaseCommand

from tasks.apps.tree.tasks import remove_quick_notes_after


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "minutes",
            type=int,
            help="Remove all older notes than N minutes",
            default=1440,
        )


    def handle(self, *args, **options):
        remove_quick_notes_after(minutes=options['minutes'])