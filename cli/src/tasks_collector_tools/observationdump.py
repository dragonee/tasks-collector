"""Dump observations to markdown files.

Usage: 
    observationdump [options] PATH

Options:
    --open           Dump only open observations.
    --closed         Dump only closed observations.
    -d DATE_FROM, --from FROM  Dump from specific date.
    -D DATE_TO, --to DATE_TO   Dump to specific date.
    -f, --force      Overwrite existing files.
    --stream ID      Dump object with specific Event Stream ID.
    --year YEAR      Dump specific year.
    -h, --help       Show this message.
    --version        Show version information.
"""

VERSION = '1.1'

import json, os, re, sys, pprint

from docopt import docopt

from datetime import datetime

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config.tasks import TasksConfigFile

from slugify import slugify

from urllib.parse import urlencode

from dateutil.parser import parse

from dataclasses import dataclass, asdict, field


TEMPLATE = """
> Date: {published}
> Thread: {thread}
> Type: {type}
> Closed: {closed}

# Situation (What happened?)

{situation}

# Interpretation (How you saw it, what you felt?)

{interpretation}

# Approach (How should you approach it in the future?)

{approach}

# Events

{events}

"""

@dataclass
class Observation:
    event_stream_id: str
    type: str = None
    thread: str = None
    published: datetime = None
    last_event_published: datetime = None
    situation: str = None
    interpretation: str = None
    approach: str = None
    updates: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    closed: bool = False

def transform_dict(dct, **kwargs):
    """
    Transform dict with functions defined in kwargs. 
    Leave other fields as is.
    """

    dct_copy = dct.copy()

    for k, f in kwargs.items():
        dct_copy[k] = f(dct[k])
    
    return dct_copy

def template_from_payload(payload, template, **kwargs):
    new_payload = transform_dict(
        payload,
        **kwargs,
    )

    return template.format(**new_payload).lstrip()


def strip_field(value):
    """Strip field from \r, leaving only \n"""
    return value.replace('\r', '') if value is not None else ''


UPDATE_TEMPLATE = """
## {resourcetype}: {published}

{comment}
"""

RECONTEXTUALIZED_TEMPLATE = """
## Recontextualized: {published}

{situation}

"""

REINTERPRETED_TEMPLATE = """

## Reinterpreted: {published}

{interpretation}

"""

REFLECTED_UPON_TEMPLATE = """   

## Reflected upon: {published}

{approach}

"""

def datetime_to_string(datetime_obj):
    return datetime_obj.strftime('%Y-%m-%d %H:%M:%S')

def event_template_from_payload(event):
    if event['resourcetype'] == 'ObservationClosed':
        return "## Closed on {}\n".format(event['published'])
    if event['resourcetype'] == 'ObservationUpdated':
        return template_from_payload(event, UPDATE_TEMPLATE, comment=strip_field, published=datetime_to_string)
    if event['resourcetype'] == 'ObservationMade':
        return "## Opened on {}\n".format(event['published'])
    if event['resourcetype'] == 'ObservationRecontextualized':
        return template_from_payload(event, RECONTEXTUALIZED_TEMPLATE, situation=strip_field, old_situation=strip_field, published=datetime_to_string)
    if event['resourcetype'] == 'ObservationReinterpreted':
        return template_from_payload(event, REINTERPRETED_TEMPLATE, interpretation=strip_field, old_interpretation=strip_field, published=datetime_to_string)
    if event['resourcetype'] == 'ObservationReflectedUpon':
        return template_from_payload(event, REFLECTED_UPON_TEMPLATE, approach=strip_field, old_approach=strip_field, published=datetime_to_string)


def events_template_from_payload(events):
    return '\n'.join(event_template_from_payload(event) for event in events)


def observation_template_from_payload(payload):
    return template_from_payload(
        payload, 
        TEMPLATE,
        situation=strip_field,
        interpretation=strip_field,
        approach=strip_field,
        closed=lambda x: 'Yes' if x else 'No',
        published=datetime_to_string,
        events=events_template_from_payload,
    )


def write_observation(observation: Observation, path, force=False):
    text = observation_template_from_payload(asdict(observation))

    filename = '{}-{}.md'.format(
        observation.published.strftime('%Y-%m-%d'),
        slugify(observation.situation, max_length=32, word_boundary=True)
    )

    new_file = path / filename

    if new_file.exists() and not force:
        return

    with open(path / filename, 'w') as f:
        f.write(text)
    
    return filename


def params_from_arguments(arguments):
    def _params_from_arguments(arguments):

        if arguments['--stream']:
            return {
                'event_stream_id': arguments['--stream']
            }
        if arguments['--year']:
            year = arguments['--year']

            return {
                'published__gte': f'{year}-01-01 00:00:00',
                'published__lte': f'{year}-12-31 23:59:59',
            }

        if arguments['--from']:
            return {
                'published__gte': arguments['--from'] + ' 00:00:00',
                'published__lte': arguments['--to'] or datetime.now(),
            }
        
        return {}
    
    params = _params_from_arguments(arguments)
    params.update({
        'features': 'updates',
    })

    if arguments['--open']:
        params['open'] = 'true'
        
    if arguments['--closed']:
        params['open'] = 'false'

    return params


def update_observation_with_event(observation: Observation, event: dict):
    event = transform_dict(event, published=parse)

    if event['resourcetype'] in ('ObservationMade', 'ObservationClosed'):
        observation.published = event['published']

    # Track the last event timestamp
    if observation.last_event_published is None or event['published'] > observation.last_event_published:
        observation.last_event_published = event['published']

    if 'type' in event:
        observation.type = event['type']
    if 'thread' in event:
        observation.thread = event['thread']
    if 'situation' in event:
        observation.situation = event['situation']
    if 'interpretation' in event:
        observation.interpretation = event['interpretation']
    if 'approach' in event:
        observation.approach = event['approach']

    if event['resourcetype'] == 'ObservationClosed':
        observation.closed = True
    if event['resourcetype'] == 'ObservationUpdated':
        observation.updates.append(event)

    observation.events.append(event)


def main():
    arguments = docopt(__doc__, version=VERSION)

    directory = Path(arguments['PATH']).resolve(strict=True)

    config = TasksConfigFile()

    url = '{}/observation-events/?{}'.format(
        config.url, 
        urlencode(params_from_arguments(arguments)),
    )

    auth = HTTPBasicAuth(config.user, config.password)

    observations = {}

    while url:
        r = requests.get(url, auth=auth)

        out = r.json()

        if not r.ok:
            raise RuntimeError("{}: {}".format(r.status_code, str(out)))

        if not 'results' in out:
            out = {
                'results': [out],
                'next': None
            }

        for item in out['results']:
            event_stream_id = item['event_stream_id']

            if event_stream_id not in observations:
                observations[event_stream_id] = Observation(event_stream_id=event_stream_id)
            
            update_observation_with_event(observations[event_stream_id], item)

        url = out['next']

    for observation in observations.values():
        # Skip observations that didn't start in a given time range
        if not any(event['resourcetype'] == 'ObservationMade' for event in observation.events):
            continue

        filename = write_observation(observation, directory, force=arguments['--force'])

        if filename:
            print('Create {}'.format(filename))

