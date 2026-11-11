"""Dump reflections and journals to markdown."""

import json
import os
import pprint
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, field
from datetime import date, datetime, timedelta
from pathlib import Path
from textwrap import dedent, fill
from typing import List, Type
from urllib.parse import urlencode

import requests
from dateutil.parser import parse
from requests.exceptions import RequestException
from slugify import slugify

from .config.tasks import TasksConfigFile
from .days import get_days
from .models import (
    Event,
    Habit,
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
{{ title }}
{% if show_summary %}
{{ reflections.good }}

{{ better_header }}

{{ reflections.better }}

{{ best_header }}

{{ reflections.best }}
{% endif %}

{% if has_plans %}
{{ plans_header }}
{% endif %}
{% if plans.focus %}
{{ plans.focus }}
{% endif %}

{% if habits.habit_groups %}
{{ habits_header }}

{{ habits.habit_groups }}
{% endif %}
{% if observation_stats.count %}
{{ observations_header }}

{{ observation_stats.renders }}
{% endif %}
{% if journals %}
{{ journals_header }}

{{ journals }}
{% endif %}
"""


def first_line(text):
    splitted = text.split("\n")

    if len(splitted) > 1:
        return splitted[0].rstrip().rstrip(".…") + "…"

    return text


TIME_FORMAT = "(%a) %H:%M"
DAILY_TIME_FORMAT = "%H:%M"


def parse_result(result_data: dict) -> Result:
    return Result.model_validate(result_data)


# A line of a plan or a reflection: an optional "- [x] " in front, and the
# anchor of its task at the end.
LINE_RE = re.compile(
    r"^\s*(?:[-*+]\s+)?(?:\[[x~^ ]\]\s+)?(?P<text>.*?)(?:[ \t]+\^t(?P<anchor>[0-9a-f]{8}))?\s*$"
)


def lines_of(text):
    """The lines of a plan's or a reflection's text, each {"text", "anchor"}."""
    return [
        LINE_RE.match(line).groupdict()
        for line in (text or "").splitlines()
        if line.strip()
    ]


def situation_of(event: ObservationEvent):
    return getattr(event, "situation", None) or getattr(
        event, "situation_at_creation", None
    )


def as_data(results: List[Result], arguments):
    """What --json prints: each day with something on it, its reflection
    and plan line by line, its habits, observations and journals; the
    sections the options leave out of the markdown are left out here too."""
    days = []

    for result in results:
        day = {"date": result.date.isoformat()}

        if not arguments.no_summary:
            reflection = result.reflection
            day["reflection"] = {
                field: lines_of(getattr(reflection, field) if reflection else None)
                for field in ("good", "better", "best")
            }

        day["plan"] = lines_of(result.plan.focus if result.plan else None)

        if not arguments.no_habits:
            day["habits"] = [
                {
                    "habit": event.habit.name,
                    "keywords": event.habit.keywords,
                    "occured": event.occured,
                    "note": event.note,
                    "published": event.published.isoformat(),
                }
                for event in result.events
                if isinstance(event, HabitTracked)
            ]

        if not arguments.no_observations:
            day["observations"] = [
                {
                    "event": event.resourcetype,
                    "observation": event.event_stream_id,
                    "situation": situation_of(event),
                    "url": getattr(event, "url", None),
                    "published": event.published.isoformat(),
                }
                for event in result.events
                if isinstance(event, ObservationEvent)
            ]

        if not arguments.skip_journals:
            day["journals"] = [
                {
                    "published": event.published.isoformat(),
                    # tc sends a comment's lines ending in \r\n.
                    "comment": event.comment.replace("\r\n", "\n"),
                    "tags": event.tags,
                }
                for event in result.events
                if isinstance(event, JournalAdded)
            ]

        days.append(day)

    return {"thread": arguments.thread or "Daily", "days": days}


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


class HabitGroup:
    def __init__(self, habit: Habit):
        self.count = 0
        self.days = set()
        self.items = []
        self.name = habit.name

    def add(self, habit_tracked: HabitTracked):
        self.count += 1 if habit_tracked.occured else 0
        self.days.add(habit_tracked.published.strftime("%a"))
        if habit_tracked.note:
            self.items.append(habit_tracked.note)


class HabitStatistics:
    habits: List[HabitTracked]

    def __init__(self, habits: List[HabitTracked]):
        self.habits = habits

    def get_context(self):
        habit_groups = {}

        for habit_tracked in self.habits:
            if habit_tracked.habit.id not in habit_groups:
                habit_groups[habit_tracked.habit.id] = HabitGroup(habit_tracked.habit)
            habit_groups[habit_tracked.habit.id].add(habit_tracked)

        return {
            "habit_groups": "\n".join(
                f"- {habit_group.name}: {habit_group.count} times on {', '.join(habit_group.days)}\n"
                + "\n".join(f"  - {note}" for note in habit_group.items)
                for habit_group in habit_groups.values()
            )
        }


class ResultAggregator:
    results: List[Result]

    def __init__(
        self,
        results: List[Result],
        skip_journals: bool = False,
        skip_summary: bool = False,
        skip_titles: bool = False,
        skip_habits: bool = False,
        skip_observations: bool = False,
        journal_prefix: str = "",
    ):
        self.results = results
        self.skip_journals = skip_journals
        self.skip_summary = skip_summary
        self.skip_titles = skip_titles
        self.skip_habits = skip_habits
        self.skip_observations = skip_observations
        self.journal_prefix = journal_prefix

    def _get_events(self, event_type: Type[Event]):
        return [
            event
            for result in self.results
            for event in result.events
            if isinstance(event, event_type)
        ]

    def get_reflections(self):
        return [result.reflection for result in self.results]

    def get_plans(self):
        return [result.plan for result in self.results]

    def get_observation_events(self):
        return self._get_events(ObservationEvent)

    def get_journal_events(self):
        return self._get_events(JournalAdded)

    def get_habit_events(self):
        return self._get_events(HabitTracked)

    def get_observation_stats(self):
        return ObservationStatistics(self.get_observation_events())

    def get_reflection_context(self):
        presenters = [
            get_reflection_presenter(result.reflection)
            for result in self.results
            if result.reflection
        ]

        return {
            "good": "\n\n".join(
                presenter.good_list(prefix="- [ ] ") for presenter in presenters
            ),
            "better": "\n\n".join(
                presenter.better_list(prefix="- [ ] ") for presenter in presenters
            ),
            "best": "\n\n".join(
                presenter.best_list(prefix="- [ ] ") for presenter in presenters
            ),
        }

    def get_plan_context(self):
        presenters = [
            get_plan_presenter(result.plan) for result in self.results if result.plan
        ]

        return {
            "focus": "\n\n".join(
                presenter.focus_list(prefix="- [ ] ") for presenter in presenters
            ),
        }

    def _render_events(self, events: List[Event], separator="\n"):
        time_format = DAILY_TIME_FORMAT if len(self.results) == 1 else TIME_FORMAT
        return separator.join(
            get_presenter(event, time_format=time_format).render() for event in events
        )

    def render_habit_events(self):
        return self._render_events(self.get_habit_events())

    def render_journal_events(self):
        rendered = self._render_events(self.get_journal_events()).strip("\n")
        if self.journal_prefix and rendered:
            rendered = "\n".join(
                self.journal_prefix + line for line in rendered.split("\n")
            )
        return rendered

    def get_title(self):
        if len(self.results) == 0:
            return "Reflection"

        if len(self.results) == 1:
            return "Reflection on {}".format(
                self.results[0].date.strftime("%-d %B (%A)"),
            )

        return "Reflection from {} to {}".format(
            self.results[0].date.strftime("%-d %B (%A)"),
            self.results[-1].date.strftime("%-d %B (%A)"),
        )

    def get_context(self):
        has_plans = any(result.plan for result in self.results)

        habits = (
            {"habit_groups": ""}
            if self.skip_habits
            else HabitStatistics(self.get_habit_events()).get_context()
        )
        observation_stats = (
            {"count": 0, "renders": ""}
            if self.skip_observations
            else self.get_observation_stats().get_context()
        )

        show_titles = not self.skip_titles

        return {
            "title": ("# " + self.get_title()) if show_titles else "",
            "better_header": "## Better" if show_titles else "",
            "best_header": "## Best" if show_titles else "",
            "plans_header": "# Plans" if show_titles else "",
            "habits_header": "# Habits" if show_titles else "",
            "observations_header": (
                f'# Work on observations ({observation_stats["count"]})'
                if show_titles
                else ""
            ),
            "journals_header": "# Journals" if show_titles else "",
            "show_summary": not self.skip_summary,
            "reflections": self.get_reflection_context(),
            "has_plans": has_plans,
            "plans": self.get_plan_context(),
            "habits": habits,
            "journals": (
                self.render_journal_events() if not self.skip_journals else None
            ),
            "observation_stats": observation_stats,
        }


def parse_arguments(argv, prog):
    parser = command_parser(prog, __doc__)

    parser.add_argument("-T", "--thread", help="Dump specific thread.")
    parser.add_argument("--skip-journals", action="store_true", help="Skip journals.")
    parser.add_argument(
        "--no-summary", action="store_true", help="Skip Good/Better/Best summary."
    )
    parser.add_argument(
        "--no-titles",
        action="store_true",
        help='Skip section headers ("# Reflection", "# Journals", etc).',
    )
    parser.add_argument("--no-habits", action="store_true", help="Skip habits section.")
    parser.add_argument(
        "--no-observations", action="store_true", help="Skip observations section."
    )
    parser.add_argument(
        "--prefix", help="Prefix each line of journal entries with PREFIX."
    )
    parser.add_argument(
        "--anchors",
        action="store_true",
        help="End each task's line with its anchor (^t...), for text that is sent back.",
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
    parser.add_argument(
        "-M",
        "--missing",
        action="store_true",
        help="Print only dates without reflection entries.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON in place of markdown: day by day, the reflection and"
        " plan line by line (each line's text and its task's anchor), habits,"
        " observations and journals.",
    )

    return parser.parse_args(argv)


def main(argv, prog):
    arguments = parse_arguments(argv, prog)

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

    def date_range(start_date, end_date, delta=timedelta(days=1)):
        current_date = start_date
        while current_date <= end_date:
            yield current_date
            current_date += delta

    try:
        fetched = get_days(
            config, start_date, end_date, arguments.thread, arguments.anchors
        )
    except (RequestException, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    results = {result.date: result for result in map(parse_result, fetched)}

    if arguments.missing:
        for dt in date_range(start_date, end_date):
            result = results.get(dt)
            if result is None or not result.reflection or result.reflection.empty():
                print(dt.strftime("%Y-%m-%d"))

        return

    valid_results = [results[dt] for dt in sorted(results) if not results[dt].empty()]

    if arguments.json:
        print(
            json.dumps(
                {
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                    **as_data(valid_results, arguments),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    aggregator = ResultAggregator(
        valid_results,
        skip_journals=arguments.skip_journals,
        skip_summary=arguments.no_summary,
        skip_titles=arguments.no_titles,
        skip_habits=arguments.no_habits,
        skip_observations=arguments.no_observations,
        journal_prefix=arguments.prefix or "",
    )
    print(render_template(TEMPLATE, aggregator.get_context()))
