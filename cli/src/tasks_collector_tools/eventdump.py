"""Dump observations to markdown files.

Usage:
    eventdump [options] [PATH]

Options:
    -d DATE_FROM, --from FROM  Dump from specific date.
    -D DATE_TO, --to DATE_TO   Dump to specific date.
    --year YEAR      Dump specific year.
    -T THREAD, --thread THREAD Dump specific thread.
    --no-plans       Exclude plans from output.
    --no-reflections  Exclude reflections from output.
    -h, --help       Show this message.
    --version        Show version information.
"""

VERSION = '1.0'

from docopt import docopt

from datetime import datetime, date, timedelta

import requests
from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config.tasks import TasksConfigFile

from dateutil.parser import parse

from textwrap import fill

from typing import List

from collections import Counter
from .utils import render_template
from .models import (
    JournalAdded, HabitTracked, ObservationEvent,
    ObservationMade, ObservationClosed, Result
)
from .presenters import get_presenter, get_plan_presenter, get_reflection_presenter

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
    splitted = text.split('\n')

    if len(splitted) > 1:
        return splitted[0].rstrip().rstrip('.…') + '…'

    return text


def parse_result(result_data: dict) -> Result:
    return Result.model_validate(result_data)


def get_daily_events(config: TasksConfigFile, arguments: dict, dt: date = None):
    if dt is None:
        dt = datetime.now().date()

    dt_string = '?date={}'.format(dt.strftime('%Y-%m-%d'))

    if arguments.get('--thread'):
        dt_string += '&thread={}'.format(arguments['--thread'])

    url = '{}/api/events/daily/{}'.format(
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

def render_daily_events(result: Result, print_plans=True, print_reflections=True):
    observations = [event for event in result.events if isinstance(event, ObservationEvent)]
    observation_stats = ObservationStatistics(observations)

    # Create presenters for plan and reflection
    plan_presenter = get_plan_presenter(result.plan) if result.plan and print_plans else None
    reflection_presenter = get_reflection_presenter(result.reflection) if result.reflection and print_reflections else None

    dct = {
        'date': result.date.strftime('%-d %B (%A)'),
        'habits': '\n'.join(get_presenter(event).render() for event in result.events if isinstance(event, HabitTracked)),
        'events': '\n'.join(get_presenter(event).render() for event in result.events if isinstance(event, JournalAdded)),
        'plan': plan_presenter,
        'reflection': reflection_presenter,
        'observation_stats': observation_stats.get_context(),
    }

    rendered = render_template(TEMPLATE, dct)

    return wrap_text_preserve_linebreaks(rendered)


def save_to_file(directory: Path, dt: date, rendered: str):
    file_path = directory / f'{dt.strftime("%m-%B").lower()}.md'
    
    with open(file_path, 'a') as f:
        f.write(rendered)


def delete_file_if_needed(already_deleted: set,directory: Path, dt: date):
    file_path = directory / f'{dt.strftime("%m-%B").lower()}.md'
    
    if file_path.exists() and file_path not in already_deleted:
        file_path.unlink()
        already_deleted.add(file_path)

def main():
    arguments = docopt(__doc__, version=VERSION)

    path = arguments['PATH']

    if path:
        directory = Path(path).resolve(strict=True)
    
    config = TasksConfigFile()

    year = int(arguments['--year']) if arguments['--year'] else None

    if year:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
    else:
        start_date = parse(arguments['--from']).date() if arguments['--from'] else datetime.now().date()
        end_date = parse(arguments['--to']).date() if arguments['--to'] else start_date

    def date_range(start_date, end_date, delta):
        current_date = start_date
        while current_date <= end_date:
            yield current_date
            current_date += delta

    already_deleted = set()

    for dt in date_range(start_date, end_date, timedelta(days=1)):
        if path:
            print("Processing... {}".format(dt), "\r", end='')

        result = get_daily_events(config, arguments, dt)

        if result.empty():
            continue

        rendered = render_daily_events(
            result,
            print_plans=not arguments['--no-plans'],
            print_reflections=not arguments['--no-reflections']
        )

        if path:
            delete_file_if_needed(already_deleted, directory, dt)
            save_to_file(directory, dt, rendered)
        else:
            print(rendered)
    
    if path:
        print("\nDone.")


