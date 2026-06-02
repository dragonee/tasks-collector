"""Add an observation.

Usage:
    observation [options]

Options:
    -l, --list       List last couple of observations.
    -a, --all        With -l, show all observations (not just mine).
    -n, --number N   With -l, show N observations [default: {observation_list_count}].
    -c, --chars N    With -l, show N chars of the situation [default: {observation_list_characters}].
    -u, --sort-by-update  With -l, sort by last event time (most recent first).
    --date DATE      Use specific date.
    -s, --save       Save as default for updates [default: False].
    --thread THREAD  Use specific thread [default: big-picture].
    --type TYPE      Choose type [default: observation].
    -h, --help       Show this message.
    --version        Show version information.
"""

TEMPLATE = """
> Date: {pub_date}
> Thread: {thread}
> Type: {type}

# Situation (What happened?)

{situation}

# Interpretation (How you saw it, what you felt?)

{interpretation}

# Approach (How should you approach it in the future?)

{approach}

"""

GOTOURL = """
See more:
- {url}/observations/{id}/
"""

import json, os, re, sys

from docopt import docopt

from datetime import datetime

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import ConnectionError, ReadTimeout

from colored import fg, attr

from .config.tasks import TasksConfigFile

from .utils import sanitize_fields, SHORT_TIMEOUT, ensure_directory_exists, queue_failed_request, retry_failed_requests


OBSERVATIONS_BACKUP_FILE = os.path.expanduser(os.path.join('~', '.tasks', 'observations_backup.json'))


def parse_datetime_delta(date_string_or_seconds: str | int | None) -> int | None:
    """Parse date string and return seconds elapsed since now.

    If seconds (int) is provided, returns it directly (identity function).
    If a date string is provided, parses it and calculates elapsed time.
    Returns None if parsing fails.
    """
    if not date_string_or_seconds and date_string_or_seconds != 0:
        return None

    # If already seconds (int), return directly
    if isinstance(date_string_or_seconds, int):
        return date_string_or_seconds

    try:
        from dateutil.parser import parse
        last_event = parse(date_string_or_seconds)

        # Make sure both datetimes are timezone-aware or both are naive
        now = datetime.now()
        if last_event.tzinfo is not None:
            from datetime import timezone
            now = datetime.now(timezone.utc)

        delta = now - last_event
        return int(delta.total_seconds())
    except Exception:
        return None


def get_age_color(seconds):
    """Get color based on age thresholds.

    - Current (< 1 week): yellow
    - Recent (1 week - 1 month): green
    - Stale (1 month - 3 months): no color
    - Old (> 3 months): blue
    """
    WEEK = 604800
    MONTH = 2592000
    THREE_MONTHS = 7776000

    if seconds < WEEK:
        return fg('yellow')
    elif seconds < MONTH:
        return fg('green')
    elif seconds < THREE_MONTHS:
        return ''  # No color for stale
    else:
        return fg('light_blue')


def time_ago(date_string_or_seconds: str | int | None) -> str:
    """Calculate time ago from a date string or seconds with multiple units."""
    seconds = parse_datetime_delta(date_string_or_seconds)
    if seconds is None:
        return ""

    if seconds < 60:
        return "just now"

    # Time units in seconds
    units = [
        ('y', 31536000),  # 365 days
        ('mo', 2592000),  # 30 days
        ('w', 604800),    # 7 days
        ('d', 86400),     # 1 day
        ('h', 3600),      # 1 hour
        ('m', 60),        # 1 minute
    ]

    parts = []
    remaining = seconds

    for unit_name, unit_seconds in units:
        if remaining >= unit_seconds:
            value = remaining // unit_seconds
            remaining = remaining % unit_seconds
            parts.append(f"{value}{unit_name}")

    # Return up to 2 most significant units
    if parts:
        return " ".join(parts[:2]) + " ago"
    else:
        return "just now"


def time_ago_colored(date_string_or_seconds: str | int | None) -> str:
    """Calculate time ago and return with color based on age."""
    seconds = parse_datetime_delta(date_string_or_seconds)
    if seconds is None:
        return ""

    text = time_ago(seconds)
    color = get_age_color(seconds)

    if color:
        return f"{color}{text}{attr('reset')}"

    return text


def template_from_arguments(arguments):
    return TEMPLATE.format(
        pub_date=arguments['--date'] or datetime.today().strftime('%Y-%m-%d'),
        thread=arguments['--thread'],
        type=arguments['--type'],
        situation='',
        interpretation='',
        approach=''
    ).lstrip()


def template_from_payload(payload):
    return TEMPLATE.format(**payload).lstrip()

OBSERVATION_FILE_PATH = os.path.expanduser(os.path.join('~', '.observation_id'))

title_re = re.compile(r'^# (Situation|Interpretation|Approach)')
meta_re = re.compile(r'^> (Date|Thread|Type): (.*)$')


def add_meta_to_payload(payload, name, item):
    if name == 'Date':
        name = 'pub_date'

    payload[name.lower()] = item


def add_stack_to_payload(payload, name, lines):
    payload[name.lower()] = ''.join(lines).strip()
        

def list_observations(config, chars=70, number=10, ownership='mine', sort_by_update=False):
    if ownership == 'mine':
        url = '{}/observation-api/?page_size={}&ownership=mine'.format(config.url, number)
    else:
        url = '{}/observation-api/?page_size={}'.format(config.url, number)

    try:
        r = requests.get(url, auth=HTTPBasicAuth(config.user, config.password), timeout=SHORT_TIMEOUT)

        if not r.ok:
            try:
                print(json.dumps(r.json(), indent=4, sort_keys=True))
            except json.decoder.JSONDecodeError:
                print("HTTP {}\n{}".format(r.status_code, r.text))

            sys.exit(1)

        response = r.json()

        ensure_directory_exists(OBSERVATIONS_BACKUP_FILE)
        with open(OBSERVATIONS_BACKUP_FILE, 'w') as f:
            json.dump(response, f)
    except (ConnectionError, ReadTimeout):
        try:
            with open(OBSERVATIONS_BACKUP_FILE, 'r') as f:
                response = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("Network unavailable and no local backup file found.")
            sys.exit(1)

    if not 'results' in response:
        print("No observations found.")
        return

    results = response['results']

    # Sort by last event time if requested
    # XXX: move to api?
    if sort_by_update:
        results = sorted(
            results,
            key=lambda item: item.get('last_event_published', '')
        )

    for item in results:
        situation_text = re.sub(r'\s+', ' ', item['situation'])[:chars]

        # Add time since last update if available
        time_info = ""
        if 'last_event_published' in item and item['last_event_published']:
            time_info = f" - {time_ago_colored(item['last_event_published'])}"

        print("#{}: {}{}".format(
            item['id'],
            situation_text,
            time_info
        ))
        

def main():
    config = TasksConfigFile()

    arguments = docopt(__doc__.format(
        observation_list_count=config.observation_list_count,
        observation_list_characters=config.observation_list_characters,
    ), version='1.0.2')

    if arguments['--list']:
        ownership = 'all' if arguments['--all'] else 'mine'
        list_observations(
            config,
            int(arguments['--chars']),
            int(arguments['--number']),
            ownership,
            arguments['--sort-by-update']
        )

        return

    tmpfile = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md')

    template = template_from_arguments(arguments)

    with tmpfile:
        tmpfile.write(template)
    
    editor = os.environ.get('EDITOR', 'vim')

    result = subprocess.run([
        editor, '+7', tmpfile.name
    ])

    if result.returncode != 0:
        sys.exit(1)

    payload = {
        'pub_date': None,
        'thread': None,
        'type': None,
        'situation': None,
        'interpretation': None,
        'approach': None,
    }

    with open(tmpfile.name) as f:
        current_name = None
        current_stack = []

        for line in f:
            if m := meta_re.match(line):
                add_meta_to_payload(payload, m.group(1).strip(), m.group(2).strip())
            elif m := title_re.match(line):
                if current_name is not None:
                    add_stack_to_payload(payload, current_name, current_stack)
                
                current_name = m.group(1).strip()
                current_stack = []
            else:
                current_stack.append(line)
    
        if current_name is not None:
            add_stack_to_payload(payload, current_name, current_stack)

    payload = sanitize_fields(payload)
    
    if not payload['situation']:
        print("No changes were made to the Situation field.")

        os.unlink(tmpfile.name)

        sys.exit(0)

    url = '{}/observation-api/'.format(config.url)

    try:
        retry_failed_requests(metadata={
            'auth': HTTPBasicAuth(config.user, config.password)
        })
    except Exception as e:
        print(e)
        print("Error: Failed to send queue")

    try:
        r = requests.post(url, json=payload, auth=HTTPBasicAuth(config.user, config.password))
    except ConnectionError:
        name = queue_failed_request(payload, metadata={
            'url': url,
        }, file_type="observation")

        print("Error: Connection failed.")
        print(f"Your update was saved at {name}.")
        print("It will be sent next time you run this program.")

        sys.exit(2)

    if r.ok:
        new_payload=r.json()

        print(template_from_payload(new_payload))

        print(GOTOURL.format(url=config.url, id=new_payload['id']).strip())

        os.unlink(tmpfile.name)

        if arguments['--save']:
            with open(OBSERVATION_FILE_PATH, 'w') as f:
                f.write(str(new_payload['id']) + "\n")
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))
        
        print("The temporary file was saved at {}".format(
            tmpfile.name
        ))



        
            

            
