"""Add update to an observation.

Usage: 
    update [options] [ID]

Options:
    -h, --help       Show this message.
    --version        Show version information.
"""

TEMPLATE = """
# Comment ({published})

{comment}

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
from requests.exceptions import ConnectionError

from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config.tasks import TasksConfigFile
from .utils import queue_failed_request, retry_failed_requests


def template_from_arguments(arguments):
    return TEMPLATE.format(
        comment='',
        published=datetime.now(),
    ).lstrip()


def template_from_payload(payload):
    return TEMPLATE.format(**payload).lstrip()

title_re = re.compile(r'^# (Comment)')
meta_re = re.compile(r'^> (Nonexistent): (.*)$')


def add_meta_to_payload(payload, name, item):
    pass

def add_stack_to_payload(payload, name, lines):
    payload[name.lower()] = ''.join(lines).strip()


OBSERVATION_FILE_PATH = os.path.expanduser(os.path.join('~', '.observation_id'))


def get_saved_observation_id():
    try:
        with open(OBSERVATION_FILE_PATH) as f:
            return int(f.read(32).strip())
    except FileNotFoundError as e:
        pass
    
    return None


def main():
    arguments = docopt(__doc__, version='1.0.2')

    config = TasksConfigFile()

    tmpfile = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md')

    template = template_from_arguments(arguments)

    observation_id = arguments['ID'] or get_saved_observation_id()

    if not observation_id:
        print("Error: No Observation ID was given.")

        sys.exit(1)

    with tmpfile:
        tmpfile.write(template)
    
    editor = os.environ.get('EDITOR', 'vim')

    result = subprocess.run([
        editor, '+3', tmpfile.name
    ])

    if result.returncode != 0:
        sys.exit(1)

    payload = {
        'comment': None,
        'observation': observation_id
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


    if payload['comment'] == '':
        print("No changes were made to the Comment field.")

        os.unlink(tmpfile.name)

        sys.exit(0)

    try:
        retry_failed_requests(metadata={
            'auth': HTTPBasicAuth(config.user, config.password)
        })
    except Exception as e:
        print(e)
        print("Error: Failed to send queue")

    url = '{}/updates/'.format(config.url)

    try:
        r = requests.post(url, json=payload, auth=HTTPBasicAuth(config.user, config.password))
    except ConnectionError:
        name = queue_failed_request(payload, metadata={
            'url': url,
        }, file_type="update")

        print("Error: Connection failed.")
        print(f"Your update was saved at {name}.")
        print("It will be sent next time you run this program.")

        sys.exit(2)

    if r.ok:
        new_payload = r.json()

        print(template_from_payload(new_payload))

        print(GOTOURL.format(url=config.url, id=new_payload['observation']).strip())

        os.unlink(tmpfile.name)

        with open(OBSERVATION_FILE_PATH, 'w') as f:
            f.write(str(new_payload['observation']) + "\n")
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))
        
        print("The temporary file was saved at {}".format(
            tmpfile.name
        ))



        
            

            
