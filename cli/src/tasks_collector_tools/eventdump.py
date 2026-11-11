"""Dump daily events to markdown."""

import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from textwrap import fill
from typing import List

from dateutil.parser import parse
from requests.exceptions import RequestException

from .config.tasks import TasksConfigFile
from .days import get_days
from .models import (
    HabitTracked,
    JournalAdded,
    ObservationClosed,
    ObservationEvent,
    ObservationMade,
    Result,
)
from .presenters import get_plan_presenter, get_presenter, get_reflection_presenter
from .utils import command_parser, render_template

EVENT_TEMPLATE = """
### {{ resourcetype }}: {{ published }}

{{ comment }}
"""


TEMPLATE = """
# {{ date }}
{% if plan and plan.model.has_focus %}
{{ plan.focus_list }}
{% endif %}

{% if habits %}
## Habits

{{ habits }}
{% endif %}
{% if observation_stats.count %}
## Work on observations ({{ observation_stats.count }})

{{ observation_stats.renders }}
{% endif %}
{% if events %}
## Journals

{{ events }}
{% endif %}
{% if reflection %}
## Reflection
{% endif %}

{% if reflection and reflection.model.has_good %}
{{ reflection.good_list }}
{% endif %}

{% if reflection and reflection.model.has_better %}
### Better

{{ reflection.better_list }}
{% endif %}

{% if reflection and reflection.model.has_best %}
### Best

{{ reflection.best_list }}
{% endif %}
"""


def first_line(text):
    splitted = text.split("\n")

    if len(splitted) > 1:
        return splitted[0].rstrip().rstrip(".…") + "…"

    return text


def parse_result(result_data: dict) -> Result:
    return Result.model_validate(result_data)


def do_fill(text, width=80):
    # preserve links
    if any(a in text for a in ("](", "http://", "https://")):
        return text

    return fill(text, width=width)


def wrap_text_preserve_linebreaks(text, width=80):
    paragraphs = text.splitlines()

    wrapped_paragraphs = [do_fill(paragraph, width=width) for paragraph in paragraphs]

    return "\n".join(wrapped_paragraphs)


def stats(closed, added, count):
    if closed:
        return " (closed)"

    if added:
        return " (added)"

    if count > 1:
        return f" ({count} updates)"

    return ""


class ObservationStatistics:
    added: set
    closed: set
    all: set

    renders: dict
    counter: Counter
    count: int

    def __init__(self, observations: List[ObservationEvent]):
        self.added = set()
        self.closed = set()
        self.all = set()
        self.counter = Counter()
        self.situation_fields = {}
        self.renders = {}
        self.count = len(observations)
        self.urls = {}
        for observation in observations:
            self.counter[observation.event_stream_id] += 1
            self.all.add(observation.event_stream_id)

            if isinstance(observation, ObservationMade):
                self.added.add(observation.event_stream_id)
            elif isinstance(observation, ObservationClosed):
                self.closed.add(observation.event_stream_id)

            if hasattr(observation, "url"):
                self.urls[observation.event_stream_id] = observation.url

            if hasattr(observation, "situation"):
                self.situation_fields[observation.event_stream_id] = (
                    observation.situation
                )
            elif hasattr(observation, "situation_at_creation"):
                self.situation_fields[observation.event_stream_id] = (
                    observation.situation_at_creation
                )

        for id in self.all:
            _stats = stats(id in self.closed, id in self.added, self.counter[id])

            self.renders[id] = "- [{situation}]({url}){updates}".format(
                situation=first_line(self.situation_fields.get(id) or "No situation"),
                url=self.urls[id],
                updates=_stats,
            )

    def get_context(self):
        return {
            "count": self.count,
            "renders": "\n".join(self.renders.values()),
        }


def render_daily_events(result: Result, print_plans=True, print_reflections=True):
    observations = [
        event for event in result.events if isinstance(event, ObservationEvent)
    ]
    observation_stats = ObservationStatistics(observations)

    # Create presenters for plan and reflection
    plan_presenter = (
        get_plan_presenter(result.plan) if result.plan and print_plans else None
    )
    reflection_presenter = (
        get_reflection_presenter(result.reflection)
        if result.reflection and print_reflections
        else None
    )

    dct = {
        "date": result.date.strftime("%-d %B (%A)"),
        "habits": "\n".join(
            get_presenter(event).render()
            for event in result.events
            if isinstance(event, HabitTracked)
        ),
        "events": "\n".join(
            get_presenter(event).render()
            for event in result.events
            if isinstance(event, JournalAdded)
        ),
        "plan": plan_presenter,
        "reflection": reflection_presenter,
        "observation_stats": observation_stats.get_context(),
    }

    rendered = render_template(TEMPLATE, dct)

    return wrap_text_preserve_linebreaks(rendered)


def save_to_file(directory: Path, dt: date, rendered: str):
    file_path = directory / f'{dt.strftime("%m-%B").lower()}.md'

    with open(file_path, "a") as f:
        f.write(rendered)


def delete_file_if_needed(already_deleted: set, directory: Path, dt: date):
    file_path = directory / f'{dt.strftime("%m-%B").lower()}.md'

    if file_path.exists() and file_path not in already_deleted:
        file_path.unlink()
        already_deleted.add(file_path)


def parse_arguments(argv, prog):
    parser = command_parser(prog, __doc__)

    parser.add_argument(
        "path",
        metavar="PATH",
        nargs="?",
        help="Write one file per day to this directory instead of printing.",
    )
    parser.add_argument(
        "-d",
        "--from",
        dest="date_from",
        metavar="DATE_FROM",
        help="Dump from specific date.",
    )
    parser.add_argument(
        "-D", "--to", dest="date_to", metavar="DATE_TO", help="Dump to specific date."
    )
    parser.add_argument("--year", type=int, help="Dump specific year.")
    parser.add_argument("-T", "--thread", help="Dump specific thread.")
    parser.add_argument(
        "--no-plans", action="store_true", help="Exclude plans from output."
    )
    parser.add_argument(
        "--no-reflections", action="store_true", help="Exclude reflections from output."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the days as the server gives them, as JSON, in place of"
        " markdown.",
    )

    arguments = parser.parse_args(argv)

    if arguments.json and arguments.path:
        parser.error("--json prints; it writes no files to PATH")

    return arguments


def as_data(fetched, arguments):
    """What --json prints: the days with something on them, as the server
    gives them, without what --no-plans and --no-reflections leave out."""
    left_out = {"plan"} if arguments.no_plans else set()
    if arguments.no_reflections:
        left_out.add("reflection")

    return [
        {key: value for key, value in day.items() if key not in left_out}
        for day in fetched
        if not parse_result(day).empty()
    ]


def main(argv, prog):
    arguments = parse_arguments(argv, prog)

    path = arguments.path

    if path:
        directory = Path(path).resolve(strict=True)

    config = TasksConfigFile()

    year = arguments.year

    if year:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
    else:
        start_date = (
            parse(arguments.date_from).date()
            if arguments.date_from
            else datetime.now().date()
        )
        end_date = parse(arguments.date_to).date() if arguments.date_to else start_date

    try:
        fetched = get_days(config, start_date, end_date, arguments.thread)
    except (RequestException, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if arguments.json:
        print(
            json.dumps(
                {
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                    "thread": arguments.thread or "Daily",
                    "days": as_data(fetched, arguments),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    already_deleted = set()

    for result in map(parse_result, fetched):
        dt = result.date

        if path:
            print("Processing... {}".format(dt), "\r", end="")

        if result.empty():
            continue

        rendered = render_daily_events(
            result,
            print_plans=not arguments.no_plans,
            print_reflections=not arguments.no_reflections,
        )

        if path:
            delete_file_if_needed(already_deleted, directory, dt)
            save_to_file(directory, dt, rendered)
        else:
            print(rendered)

    if path:
        print("\nDone.")
