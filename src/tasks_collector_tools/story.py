import requests
from requests.auth import HTTPBasicAuth

from requests.exceptions import ConnectionError, ReadTimeout

from .utils import SHORT_TIMEOUT


def get_active_story(config):
    """Return the newest active story as a dict {id, title, ...} or None.

    "Active" means a story with no `stopped` timestamp. The backend orders
    stories newest-first, so the first result is the most recently started.
    Network failures degrade to None so the journal still opens.
    """
    try:
        url = '{}/stories/?active=true'.format(config.url)

        r = requests.get(
            url,
            auth=HTTPBasicAuth(config.user, config.password),
            timeout=SHORT_TIMEOUT
        )

        if not r.ok:
            return None

        results = r.json().get('results', [])

        return results[0] if results else None

    except (ConnectionError, ReadTimeout):
        return None
