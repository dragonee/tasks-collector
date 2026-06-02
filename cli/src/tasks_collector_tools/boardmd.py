"""Dump a board to markdown.

Usage: 
    boardmd [options]

Options:
    --thread THREAD  Use specific thread [default: big-picture].
    --enumerate      Add numberic enumeration to points (e.g. 1.2.4.)
    -h, --help       Show this message.
    --version        Show version information.
"""


GOTOURL = """
See more:
- {url}/observations/
"""

import json, os, re, sys, pprint

from docopt import docopt

from datetime import datetime

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config.tasks import TasksConfigFile

pattern_s = re.compile(r'\s+')

def threads_to_dict(response):
    thread_f = lambda thread: (thread['name'], thread['id'])

    return dict(map(thread_f, response['results']))


def get_board_meta(response):
    board = response['results'][0]

    return {
        'focus': board['focus'],
        'date_started': board['date_started'],
        'id': board['id'],
    }


def get_state_tree(response):
    return response['results'][0]['state']


def empty_enumerator(path):
    return ''


def dotted_enumerator(path):
    return '{}.'.format('.'.join(map(str, path)))


def state_func(item):
    is_category = '[ ]' if len(item['children']) == 0 else ''

    made_progress = '[~]' if item['data']['meaningfulMarkers']['madeProgress'] else is_category

    return '{}'.format(
        '[x]' if item['state'].get('checked', False) else made_progress
    )


def importance(item):
    imp = item['data']['meaningfulMarkers']['important']

    if imp > 0:
        return '({})'.format('!' * imp)

    return ''


def recur_print_md(tree, enumerator, path=tuple()):        
    title_str = "{} {} {} {} {}".format(
        "#" * len(path), 
        state_func(tree),
        enumerator(path), 
        tree['text'],
        importance(tree)
    )

    print(pattern_s.sub(' ', title_str).strip())
    print("")

    for i, item in enumerate(tree['children'], start=1):
        recur_print_md(item, enumerator, path + (i,))


def main():
    arguments = docopt(__doc__, version='1.0')

    config = TasksConfigFile()

    url = '{}/threads/'.format(config.url)

    auth = HTTPBasicAuth(config.user, config.password)


    r = requests.get(url, auth=auth)

    thread_dict = threads_to_dict(r.json())

    thread_id = thread_dict[arguments['--thread']]

    url2 = '{}/boards/?thread={}'.format(config.url, thread_id)

    r = requests.get(url2, auth=auth)

    out = r.json()

    meta = get_board_meta(out)
    state = get_state_tree(out)

    #pprint.pprint(state)

    enumerator = dotted_enumerator if arguments['--enumerate'] else empty_enumerator

    for i, item in enumerate(state, start=1):
        recur_print_md(
            item, 
            enumerator,
            (i,)
        )
