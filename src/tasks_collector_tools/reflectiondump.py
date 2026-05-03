"""Dump observations to markdown files.

Usage: 
    reflectiondump [options]

Options:
    -T, --thread THREAD  Dump specific thread.
    --skip-journals     Skip journals.
    --no-summary        Skip Good/Better/Best summary.
    --no-titles         Skip section headers ("# Reflection", "# Journals", etc).
    --no-habits         Skip habits section.
    --no-observations   Skip observations section.
    --prefix PREFIX     Prefix each line of journal entries with PREFIX.
    -d DATE_FROM, --from FROM  Dump from specific date.
    -D DATE_TO, --to DATE_TO   Dump to specific date.
    --year YEAR      Dump specific year.
    -M, --missing    Print only dates without reflection entries.
    -h, --help       Show this message.
    --version        Show version information.
"""

VERSION = '1.0'

import json, os, re, sys, pprint

from docopt import docopt

from datetime import datetime, date, timedelta

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException

from pathlib import Path

from .config.tasks import TasksConfigFile

from slugify import slugify

from urllib.parse import urlencode

from dateutil.parser import parse

from dataclasses import asdict, field

import re

from textwrap import dedent, fill

from typing import Type, List

from collections import Counter
from .utils import render_template
from .models import (
    Habit, JournalAdded, HabitTracked, ObservationEvent,
    ObservationMade, ObservationClosed, Event, Result
)
from .presenters import (
    get_presenter, get_plan_presenter, get_reflection_presenter
)


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
    splitted = text.split('\n')

    if len(splitted) > 1:
        return splitted[0].rstrip().rstrip('.…') + '…'

    return text

TIME_FORMAT = '(%a) %H:%M'
DAILY_TIME_FORMAT = '%H:%M'


def parse_result(result_data: dict) -> Result:
    return Result.model_validate(result_data)


def get_daily_events(config: TasksConfigFile, arguments: dict, dt: date = None):
    if dt is None:
        dt = datetime.now().date()
    
    params = {
        'date': dt.strftime('%Y-%m-%d'),
        'thread': arguments['--thread'] if arguments['--thread'] else 'Daily',
    }

    dt_string = urlencode(params)

    url = '{}/api/events/daily/?{}'.format(
        config.url, 
        dt_string,
    )

    auth = HTTPBasicAuth(config.user, config.password)

    r = requests.get(url, auth=auth)

    out = r.json()

    if not r.ok:
        raise RuntimeError("{}: {}".format(r.status_code, str(out)))

    return parse_result(out)


def do_fill(text, width=80):
    # preserve links
    if any(a in text for a in ('](', 'http://', 'https://')):
        return text

    return fill(text, width=width)


def wrap_text_preserve_linebreaks(text, width=80):
    paragraphs = text.splitlines()
    
    wrapped_paragraphs = [do_fill(paragraph, width=width) for paragraph in paragraphs]
    
    return '\n'.join(wrapped_paragraphs)


def stats(closed, added, count):
    if closed:
        return ' (closed)'

    if added:
        return ' (added)'

    if count > 1:
        return f' ({count} updates)'

    return ''

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

            if hasattr(observation, 'url'):
                self.urls[observation.event_stream_id] = observation.url

            if hasattr(observation, 'situation'):
                self.situation_fields[observation.event_stream_id] = observation.situation
            elif hasattr(observation, 'situation_at_creation'):
                self.situation_fields[observation.event_stream_id] = observation.situation_at_creation

        for id in self.all:
            _stats = stats(
                id in self.closed, 
                id in self.added, 
                self.counter[id]
            )

            self.renders[id] = '- [{situation}]({url}){updates}'.format(
                situation=first_line(self.situation_fields[id]),
                url=self.urls[id],
                updates=_stats
            )

    def get_context(self):
        return {
            'count': self.count,
            'renders': '\n'.join(self.renders.values()),
        }

class HabitGroup:
    def __init__(self, habit: Habit):
        self.count = 0
        self.days = set()
        self.items = []
        self.name = habit.name

    def add(self, habit_tracked: HabitTracked):
        self.count += 1 if habit_tracked.occured else 0
        self.days.add(habit_tracked.published.strftime('%a'))
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
            'habit_groups': '\n'.join(
                f"- {habit_group.name}: {habit_group.count} times on {', '.join(habit_group.days)}\n" +
                '\n'.join(f"  - {note}" for note in habit_group.items)
                for habit_group in habit_groups.values()
            )
        }
        
class ResultAggregator:
    results: List[Result]

    def __init__(self, results: List[Result], skip_journals: bool = False, skip_summary: bool = False, skip_titles: bool = False, skip_habits: bool = False, skip_observations: bool = False, journal_prefix: str = ''):
        self.results = results
        self.skip_journals = skip_journals
        self.skip_summary = skip_summary
        self.skip_titles = skip_titles
        self.skip_habits = skip_habits
        self.skip_observations = skip_observations
        self.journal_prefix = journal_prefix

    def _get_events(self, event_type: Type[Event]):
        return [event for result in self.results for event in result.events if isinstance(event, event_type)]
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
        presenters = [get_reflection_presenter(result.reflection) for result in self.results if result.reflection]

        return {
            'good': '\n\n'.join(presenter.good_list(prefix='- [ ] ') for presenter in presenters),
            'better': '\n\n'.join(presenter.better_list(prefix='- [ ] ') for presenter in presenters),
            'best': '\n\n'.join(presenter.best_list(prefix='- [ ] ') for presenter in presenters),
        }
    
    def get_plan_context(self):
        presenters = [get_plan_presenter(result.plan) for result in self.results if result.plan]

        return {
            'focus': '\n\n'.join(presenter.focus_list(prefix='- [ ] ') for presenter in presenters),
        }

    def _render_events(self, events: List[Event], separator='\n'):
        time_format = DAILY_TIME_FORMAT if len(self.results) == 1 else TIME_FORMAT
        return separator.join(get_presenter(event, time_format=time_format).render() for event in events)

    def render_habit_events(self):
        return self._render_events(self.get_habit_events())
    
    def render_journal_events(self):
        rendered = self._render_events(self.get_journal_events()).strip('\n')
        if self.journal_prefix and rendered:
            rendered = '\n'.join(self.journal_prefix + line for line in rendered.split('\n'))
        return rendered

    def get_title(self):
        if len(self.results) == 0:
            return 'Reflection'
        
        if len(self.results) == 1:
            return 'Reflection on {}'.format(
                self.results[0].date.strftime('%-d %B (%A)'),
            )

        return 'Reflection from {} to {}'.format(
            self.results[0].date.strftime('%-d %B (%A)'),
            self.results[-1].date.strftime('%-d %B (%A)'),
        )

    def get_context(self):
        has_plans = any(result.plan for result in self.results)

        habits = {'habit_groups': ''} if self.skip_habits else HabitStatistics(self.get_habit_events()).get_context()
        observation_stats = {'count': 0, 'renders': ''} if self.skip_observations else self.get_observation_stats().get_context()

        show_titles = not self.skip_titles

        return {
            'title': ('# ' + self.get_title()) if show_titles else '',
            'better_header': '## Better' if show_titles else '',
            'best_header': '## Best' if show_titles else '',
            'plans_header': '# Plans' if show_titles else '',
            'habits_header': '# Habits' if show_titles else '',
            'observations_header': f'# Work on observations ({observation_stats["count"]})' if show_titles else '',
            'journals_header': '# Journals' if show_titles else '',
            'show_summary': not self.skip_summary,
            'reflections': self.get_reflection_context(),
            'has_plans': has_plans,
            'plans': self.get_plan_context(),
            'habits': habits,
            'journals': self.render_journal_events() if not self.skip_journals else None,
            'observation_stats': observation_stats,
        }


def main():
    arguments = docopt(__doc__, version=VERSION)
    
    config = TasksConfigFile()

    year = int(arguments['--year']) if arguments['--year'] else None

    if year:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
    else:
        start_date = parse(arguments['--from']).date() if arguments['--from'] else datetime.now().date()
        end_date = parse(arguments['--to']).date() if arguments['--to'] else start_date

    def date_range(start_date, end_date, delta=timedelta(days=1)):
        current_date = start_date
        while current_date <= end_date:
            yield current_date
            current_date += delta

    def try_get_daily_events(dt, config, arguments):
        try:
            return get_daily_events(config, arguments, dt)
        except RequestException as e:
            print(f"Error fetching data for {dt}: {str(e)}", file=sys.stderr)
            return None

    date_results = list(map(
        lambda dt: (
            dt,
            try_get_daily_events(dt, config, arguments)
        ),
        date_range(start_date, end_date)
    ))
    
    if arguments['--missing']:
        missing_dates = [dt for dt, result in date_results if result is None or not result.reflection or result.reflection.empty()]
        
        for dt in missing_dates:
            print(dt.strftime('%Y-%m-%d'))
        
        return

    valid_results = [result for _, result in date_results 
                    if result is not None and not result.empty()]
    
    aggregator = ResultAggregator(
        valid_results,
        skip_journals=arguments['--skip-journals'],
        skip_summary=arguments['--no-summary'],
        skip_titles=arguments['--no-titles'],
        skip_habits=arguments['--no-habits'],
        skip_observations=arguments['--no-observations'],
        journal_prefix=arguments['--prefix'] or '',
    )
    print(render_template(TEMPLATE, aggregator.get_context()))


