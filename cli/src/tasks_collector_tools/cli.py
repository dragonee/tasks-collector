"""Command line for the Tasks Collector."""

import os
import sys
from dataclasses import dataclass
from importlib import import_module

from .config.tasks import CONFIG_ENV
from .utils import package_version

USAGE = """
usage: tc [--config FILE] [COMMAND] [ARGS ...]

{description}

commands:
{commands}

Without a command, tc runs `tasks`.
Run `tc COMMAND --help` for the options of a command.

tc reads /etc/tasks-collector.ini, ~/.tasks-collector.ini and
./tasks-collector.ini, a later one overriding what the ones before it say.
--config FILE (or TC_CONFIG=FILE) reads that file alone. `tc whoami` says
which were read, and who the server takes tc for.
"""


@dataclass(frozen=True)
class Route:
    """A command, the words that select it and the function that runs it.

    A word written `obs[ervation]` may be shortened down to `obs`; a word
    without brackets has to be typed in full.
    """

    spec: str
    target: str
    summary: str

    @property
    def words(self):
        """Each word as a (shortest form, full form) pair."""
        return [
            (short, short + rest.rstrip("]"))
            for short, _, rest in (word.partition("[") for word in self.spec.split())
        ]

    @property
    def prog(self):
        return " ".join(["tc", *(full for _, full in self.words)])

    def matches(self, argv):
        words = self.words

        return len(argv) >= len(words) and all(
            full.startswith(arg) and len(arg) >= len(short)
            for (short, full), arg in zip(words, argv)
        )

    def run(self, argv):
        module, function = self.target.split(":")

        return getattr(import_module(f".{module}", __package__), function)(
            argv, self.prog
        )


DEFAULT = Route("tasks", "tasks:main", "Connect to the Tasks Collector.")

ROUTES = [
    DEFAULT,
    Route("obs[ervation]", "observation:main", "Add an observation."),
    Route(
        "obs[ervation] dump",
        "observationdump:main",
        "Dump observations to markdown files.",
    ),
    Route("upd[ate]", "update:main", "Add update to an observation."),
    Route("jou[rnal]", "journal:main", "Add journal entry."),
    Route(
        "trip jou[rnal]", "journal:trip_main", "Add journal entry to the current trip."
    ),
    Route("hab[its]", "habits:main", "Track habits daily or list them."),
    Route("events dump", "eventdump:main", "Dump daily events to markdown."),
    Route("reflect", "reflect:main", "Reflect on a day, week or month."),
    Route(
        "reflect dump",
        "reflectiondump:main",
        "Dump reflections and journals to markdown.",
    ),
    # `reflect dump` of one day: today, unless -d says another.
    Route(
        "today",
        "reflectiondump:main",
        "Print today's reflection, plan, habits, observations and journals.",
    ),
    Route("board dump", "boardmd:main", "Dump a board to markdown."),
    Route("whoami", "whoami:main", "Say which server tc talks to, and as whom."),
]


def usage():
    width = max(len(route.spec) for route in ROUTES)

    return USAGE.format(
        description=__doc__,
        commands="\n".join(
            f"  {route.spec:<{width}}  {route.summary}" for route in ROUTES
        ),
    ).strip()


def resolve(argv):
    """Return the route matching the most leading words of argv, or None."""
    return max(
        (route for route in ROUTES if route.matches(argv)),
        key=lambda route: len(route.words),
        default=None,
    )


def take_config(argv):
    """argv without a leading ``--config FILE`` (or ``--config=FILE``), which
    is put into $TC_CONFIG: the commands, and those they run, read it."""
    if argv[:1] == ["--config"] and len(argv) > 1:
        os.environ[CONFIG_ENV] = argv[1]
        return argv[2:]

    if argv and argv[0].startswith("--config="):
        os.environ[CONFIG_ENV] = argv[0].removeprefix("--config=")
        return argv[1:]

    return argv


def main(argv=None):
    argv = take_config(sys.argv[1:] if argv is None else argv)

    route = resolve(argv)

    if route is not None:
        return route.run(argv[len(route.words) :])

    first = argv[0] if argv else ""

    if first in ("-h", "--help"):
        print(usage())
        return

    if first == "--version":
        print(package_version())
        return

    if first and not first.startswith("-"):
        print(f"tc: no such command: {first}\n\n{usage()}", file=sys.stderr)
        sys.exit(2)

    return DEFAULT.run(argv)
