"""Track habits daily or list them.

Usage: 
    habits [options]

Options:
    -a, --all        Track all habits.
    -d, --date DATE  Use this date for tracking habits.
    -Y, --yesterday  Set the date to yesterday.
    -l, --list       List habits
    -o, --output FILENAME  If listing, output to file [default: -]
    -h, --help       Show this message.
    --version        Show version information.
"""

import sys

import requests
from requests.auth import HTTPBasicAuth

import json

from docopt import docopt

from .config.tasks import TasksConfigFile
from .utils import smart_open

from dataclasses import dataclass

from datetime import datetime, timedelta
from dateutil.parser import parse

from .models import HabitWithTracked, Keyword


def add_habit(config, text, published=None):
    if published is None:
        published = datetime.now()

    payload = {
        'text': text,
        'published': published.astimezone().isoformat()
    }

    url = '{}/habit/track/'.format(config.url)

    r = requests.post(url, json=payload, auth=HTTPBasicAuth(config.user, config.password))

    if r.ok:
        print("Habit tracked")
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))


def format_habit_list(habits):
    keywords = ['#' + keyword for habit in habits for keyword in habit.get('keywords', [])]
    return ", ".join(keywords)


def get_habit_list(config, stderr, date=None):
    url = f"{config.url}/habit-api/"

    if date is not None:
        url += f"?date={date.isoformat()}"

    r = requests.get(url, auth=HTTPBasicAuth(config.user, config.password))

    if r.ok:
        return r.json()['results']
    else:
        try:
            stderr.write(json.dumps(r.json(), indent=4, sort_keys=True) + '\n')
        except json.decoder.JSONDecodeError:
            stderr.write("HTTP {}\n{}".format(r.status_code, r.text) + '\n')


def get_keyword_list(config, stderr, date=None, all_keywords=False):
    url = f"{config.url}/habit/keywords/mine/"

    params = {}
    if date is not None:
        params['date'] = date.date().isoformat()
    if all_keywords:
        params['all'] = 'true'

    r = requests.get(url, params=params, auth=HTTPBasicAuth(config.user, config.password))

    if r.ok:
        return [Keyword(**kw) for kw in r.json()]
    else:
        try:
            stderr.write(json.dumps(r.json(), indent=4, sort_keys=True) + '\n')
        except json.decoder.JSONDecodeError:
            stderr.write("HTTP {}\n{}".format(r.status_code, r.text) + '\n')
        return []


def print_habit_list(config, filename='-'):
    with smart_open(filename, 'w', pipe=sys.stdout) as f:
        habits = get_habit_list(config, sys.stderr)

        f.write(format_habit_list(habits) + '\n')



def match_occurrence(entry, words, no_words):
    """Match occurrence indicators and return True, False, or just the text."""
    for word in words:
        if entry.startswith(word):
            return (True, entry[len(word):].lstrip())

    for word in no_words:
        if entry.startswith(word):
            return (False, entry[len(word):].lstrip())

    # No occurrence indicator found
    return entry.strip()


def parse_pipe_entries(input_string, words, no_words):
    """Parse pipe-separated entries with occurrence inheritance."""
    entries = [entry.strip() for entry in input_string.split('|')]
    results = []
    last_occurrence = None

    for entry in entries:
        if not entry:
            continue

        match match_occurrence(entry, words, no_words):
            case (True, text):
                last_occurrence = True
                results.append((True, text))
            case (False, text):
                last_occurrence = False
                results.append((False, text))
            case text:  # Just text, no occurrence indicator
                if last_occurrence is not None:
                    results.append((last_occurrence, text))
                else:
                    # First entry has no indicator, return None to retry input
                    return None

    return results if results else None


def ask_for(words, no_words=None, skip_words=None, prompt="{words}"):
    if no_words:
        _prompt = "[{}/{}/{}] ".format(words[0], no_words[0], skip_words[0].upper())
    else:
        _prompt = "[{}/{}] ".format(words[0], skip_words[0].upper())

    prompt = prompt.format(words=_prompt)

    while True:
        original_input = input(prompt)

        # Handle empty input or skip first
        if original_input == '':
            return None

        # Check for skip words
        for skip_word in skip_words:
            if original_input.startswith(skip_word):
                return None

        # Parse entries (single or pipe-separated)
        parsed_entries = parse_pipe_entries(original_input, words, no_words)

        if parsed_entries is None:
            continue  # Invalid input, ask again

        return parsed_entries


def format_line(keyword, answer, text):
    occured = '#' if answer else '!'
    
    return f'{occured}{keyword} {text}'


def get_date_from_arguments(arguments):
    """Get the date from command line arguments."""
    if arguments['--date']:
        return parse(arguments['--date'])
    elif arguments['--yesterday']:
        return (datetime.now() - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
    
    return datetime.now()


def main():
    arguments = docopt(__doc__, version='1.1')

    config = TasksConfigFile()

    published = get_date_from_arguments(arguments)

    if arguments['--list']:
        print_habit_list(config, arguments['--output'])
        return

    keywords = get_keyword_list(config, sys.stderr, date=published, all_keywords=arguments['--all'])

    print("Tip: Use pipe separator (|) for multiple entries: y first entry | second entry | n third entry")

    try:
        for kw in keywords:
            entries = ask_for(['y', 't'], ['n', 'f'], ['s'], prompt=f'#{kw.keyword} {{words}}')

            if entries is None:
                continue

            # Process all entries for this habit
            for answer, text in entries:
                add_habit(config, format_line(kw.keyword, answer, text), published=published)
    except (KeyboardInterrupt, EOFError):
        print()
        return
