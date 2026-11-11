"""Say which server tc talks to, and as whom.

It names the configuration files read (a later one overrides what the ones
before it say), the server's address, and who the server takes tc for: the
user, and the token when tc sends one, with whether it can only read.
Exits with 1 when the server doesn't take it for anyone.
"""

import json
import sys

import requests
from requests.exceptions import RequestException

from .config.tasks import TasksConfigFile
from .utils import SHORT_TIMEOUT, command_parser


def ask_server(config):
    """What the server says of the caller (``api/v1/me/``), or {"error": …}."""
    try:
        r = requests.get(
            f"{config.url}/api/v1/me/", auth=config.auth, timeout=SHORT_TIMEOUT
        )
    except RequestException as e:
        return {"error": str(e)}

    if r.status_code == 404:
        return {"error": "the server doesn't say: it is older than this tc"}
    if not r.ok:
        return {"error": f"HTTP {r.status_code}"}
    return r.json()


def describe(info):
    server = info["server"]

    if "error" in server:
        who = f"nobody ({server['error']})"
    elif server["token"] is None:
        who = f"{server['username']}, with a password"
    else:
        token = server["token"]
        who = f"{server['username']}, with the token {token['name']!r}"
        if token["read_only"]:
            who += ", which can only read"

    return "\n".join(
        [
            f"config     {', '.join(info['config']) or 'none'}",
            f"server     {info['url']}",
            f"logged in  {who}",
        ]
    )


def parse_arguments(argv, prog):
    parser = command_parser(prog, __doc__)

    parser.add_argument("--json", action="store_true", help="Print it as JSON.")

    return parser.parse_args(argv)


def main(argv, prog):
    arguments = parse_arguments(argv, prog)

    config = TasksConfigFile()

    info = {
        "config": [str(path) for path in config.files],
        "url": config.url,
        "auth": "token" if config.token else "password",
        "server": ask_server(config),
    }

    if arguments.json:
        print(json.dumps(info, indent=2))
    else:
        print(describe(info))

    if "error" in info["server"]:
        sys.exit(1)
