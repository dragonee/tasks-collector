import subprocess

from functools import partial

from django.core.management.base import BaseCommand
from django.utils import autoreload

import argparse


def restart_celery(subcommand, *args):
    subprocess.call(['pkill', 'celery'])
    subprocess.call(['celery', '-A', 'tasks', subcommand] + list(args))


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "subcommand",
            type=str,
            help="Set to worker or beat for the scheduler",
            default="worker"
        )

        parser.add_argument("rest", nargs=argparse.REMAINDER)

    def handle(self, *args, **options):
        subcommand = options['subcommand']

        self.stdout.write(f'Starting celery {subcommand} with autoreload...')

        autoreload.run_with_reloader(partial(restart_celery, subcommand, *options['rest']))