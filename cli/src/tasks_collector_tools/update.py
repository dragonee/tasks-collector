"""Add update to an observation."""

TEMPLATE = """
# Comment ({published})

{comment}

"""

GOTOURL = """
See more:
- {url}/observations/{id}/
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import requests
from requests.exceptions import ConnectionError

from .config.tasks import TasksConfigFile
from .utils import (
    command_parser,
    queue_failed_request,
    retry_failed_requests,
    smart_open,
)


def template_from_arguments(arguments, comment=""):
    return TEMPLATE.format(
        comment=comment,
        published=datetime.now(),
    ).lstrip()


def template_from_payload(payload):
    return TEMPLATE.format(**payload).lstrip()


title_re = re.compile(r"^# (Comment)")
meta_re = re.compile(r"^> (Nonexistent): (.*)$")


def add_meta_to_payload(payload, name, item):
    pass


def add_stack_to_payload(payload, name, lines):
    payload[name.lower()] = "".join(lines).strip()


OBSERVATION_FILE_PATH = os.path.expanduser(os.path.join("~", ".observation_id"))


def get_saved_observation_id():
    try:
        with open(OBSERVATION_FILE_PATH) as f:
            return int(f.read(32).strip())
    except FileNotFoundError as e:
        pass

    return None


def parse_arguments(argv, prog):
    parser = command_parser(prog, __doc__)

    parser.add_argument(
        "id",
        metavar="ID",
        nargs="?",
        help="Observation to update [default: the one saved with `tc observation --save`].",
    )
    parser.add_argument(
        "-f",
        "--file",
        help="Start the comment with this file (- for standard input).",
    )
    parser.add_argument(
        "--no-edit",
        action="store_true",
        help="Don't open the editor: send the comment from -f as it is.",
    )

    arguments = parser.parse_args(argv)

    if arguments.no_edit and not arguments.file:
        parser.error("--no-edit needs -f FILE (or -f - for standard input)")

    return arguments


def main(argv, prog):
    arguments = parse_arguments(argv, prog)

    config = TasksConfigFile()

    observation_id = arguments.id or get_saved_observation_id()

    if not observation_id:
        print("Error: No Observation ID was given.")

        sys.exit(1)

    comment = ""

    if arguments.file:
        with smart_open(arguments.file) as f:
            comment = f.read()

    template = template_from_arguments(arguments, comment)

    # The file the editor saved; with --no-edit there is none.
    tmpname = None

    if arguments.no_edit:
        content = template
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".md"
        ) as tmpfile:
            tmpfile.write(template)
        tmpname = tmpfile.name

        editor = os.environ.get("EDITOR", "vim")

        result = subprocess.run([editor, "+3", tmpname])

        if result.returncode != 0:
            sys.exit(1)

        with open(tmpname) as f:
            content = f.read()

    payload = {"comment": None, "observation": observation_id}

    current_name = None
    current_stack = []

    for line in content.splitlines(keepends=True):
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

    if not payload["comment"]:
        print("No changes were made to the Comment field.")

        if tmpname:
            os.unlink(tmpname)

        sys.exit(1 if arguments.no_edit else 0)

    # Sent again when the update is queued and retried, so the server adds
    # it once.
    payload["idempotency_key"] = uuid.uuid4().hex

    try:
        retry_failed_requests(metadata={"auth": config.auth})
    except Exception as e:
        print(e)
        print("Error: Failed to send queue")

    url = "{}/updates/".format(config.url)

    try:
        r = requests.post(url, json=payload, auth=config.auth)
    except ConnectionError:
        name = queue_failed_request(
            payload,
            metadata={
                "url": url,
            },
            file_type="update",
        )

        print("Error: Connection failed.")
        print(f"Your update was saved at {name}.")
        print("It will be sent next time you run this program.")

        sys.exit(2)

    if r.ok:
        new_payload = r.json()

        print(template_from_payload(new_payload))

        print(GOTOURL.format(url=config.url, id=new_payload["observation"]).strip())

        if tmpname:
            os.unlink(tmpname)

        with open(OBSERVATION_FILE_PATH, "w") as f:
            f.write(str(new_payload["observation"]) + "\n")
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))

        if tmpname:
            print("The temporary file was saved at {}".format(tmpname))
        else:
            sys.exit(1)
