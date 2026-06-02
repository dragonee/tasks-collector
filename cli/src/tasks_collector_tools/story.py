import os

import requests
from requests.auth import HTTPBasicAuth

from requests.exceptions import ConnectionError, ReadTimeout

from .utils import SHORT_TIMEOUT, ensure_directory_exists

CURRENT_TRIP_FILE = os.path.expanduser(os.path.join('~', '.tasks', 'current_trip'))


def get_active_stories(config):
    """Return the list of active stories (dicts), newest first; [] on error.

    "Active" means a story with no `stopped` timestamp. Network failures
    degrade to an empty list so callers keep working offline.
    """
    try:
        url = '{}/stories/?active=true'.format(config.url)

        r = requests.get(
            url,
            auth=HTTPBasicAuth(config.user, config.password),
            timeout=SHORT_TIMEOUT
        )

        if not r.ok:
            return []

        return r.json().get('results', [])

    except (ConnectionError, ReadTimeout):
        return []


def get_active_story(config):
    """Return the newest active story as a dict {id, title, ...} or None."""
    stories = get_active_stories(config)

    return stories[0] if stories else None


def get_story(config, story_id):
    """Fetch a single story by id as a dict, or None on any failure."""
    try:
        url = '{}/stories/{}/'.format(config.url, story_id)

        r = requests.get(
            url,
            auth=HTTPBasicAuth(config.user, config.password),
            timeout=SHORT_TIMEOUT
        )

        if not r.ok:
            return None

        return r.json()

    except (ConnectionError, ReadTimeout):
        return None


def set_current_trip(story_id):
    """Persist the chosen trip id to ~/.tasks/current_trip."""
    ensure_directory_exists(CURRENT_TRIP_FILE)

    with open(CURRENT_TRIP_FILE, 'w') as f:
        f.write(str(story_id))


def get_current_trip():
    """Return the saved current trip id (int) or None if unset/unreadable."""
    try:
        with open(CURRENT_TRIP_FILE) as f:
            text = f.read().strip()
    except (FileNotFoundError, OSError):
        return None

    try:
        return int(text)
    except ValueError:
        return None
