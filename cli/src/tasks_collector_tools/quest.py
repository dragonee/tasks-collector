"""Follow a quest.

Usage: 
    quest [options] KEY [STAGE]

Options:
    -h, --help       Show this message.
    --version        Show version information.
"""

from dataclasses import dataclass, field
import json, os, re, sys

from docopt import docopt

from datetime import datetime, date

import tempfile

import subprocess

import requests
from requests.auth import HTTPBasicAuth

import yaml

from pathlib import Path

from colored import fg, attr

from .config.tasks import TasksConfigFile


JOURNAL_TEMPLATE = """
{green}{quest_name}{clear}   {gray}#{quest_slug}{clear}
-------------------------------------------------------

{text}

-------------------------------------------------------"""
FINISH_TEMPLATE = """
{gray}Quest URL: {link}
{last_line}{clear}"""

REWARD_TEMPLATE = """{yellow}Found reward!{clear}

  Go to {blue}{link}{clear} to claim it!
"""

colors = {
    'yellow': fg('yellow'),
    'green': fg('light_green_2'),
    'blue': fg('light_blue'),
    'red': fg('red'),
    'gray': fg('dark_gray'),
    'clear': attr('reset'),
}

def reward_template_from_payload(payload, config):
    return REWARD_TEMPLATE.format(
        link= "{}{}".format(config.url, payload['url']),
        **payload,
        **colors,
    )


def journal_template_from_payload(payload, config, template):
    if payload['quest']['date_closed']:
        motivational_quote = "Finished on {}.\nThanks for playing the game of your life!".format(
            payload['quest']['date_closed']
        )
    elif payload['stage'] > 0:
        motivational_quote = "Stage {} completed. You are on your way!".format(
            payload['quest']['stage']
        )
    else:
        motivational_quote = "Another stage of the quest finished!"

    return template.format(
        link="{}{}".format(config.url, payload['quest']['url']),
        padded_text= "\n".join(("  " + x for x in payload['text'].splitlines())),
        quest_stage=payload['quest']['stage'],
        quest_name=payload['quest']['name'],
        quest_slug=payload['quest']['slug'],
        quest_date_closed=payload['quest']['date_closed'] or '',
        last_line=motivational_quote,
        **payload,
        **colors,
    ).lstrip()


@dataclass
class Stage:
    stage: int = 0
    text: str = ""
    finishes: bool = False
    rewards: list[str] = field(default_factory=list)


@dataclass
class Quest:
    name: str
    stages: list[Stage] = field(default_factory=list)

    def stage(self, number):
        try:
            return next(x for x in self.stages if x.stage == number)
        except StopIteration:
            return Stage()


def load_quest_file(filepath):
    with open(filepath) as f:
        data = yaml.safe_load(f)
    
    stages = []

    for item in data['stages']:
        stages.append(Stage(**item))
    
    return Quest(name=data['name'], stages=stages)


def main():
    arguments = docopt(__doc__, version='1.0.1')

    config = TasksConfigFile()

    if not config.quest_path:
        print("quest_path in your ~/.tasks-collector.ini is not defined", file=sys.stderr)
        sys.exit(1)
    
    filepath = config.quest_path / "{}.yml".format(arguments["KEY"])

    if not filepath.exists():
        print("{} does not exist".format(filepath), file=sys.stderr)
        sys.exit(1)

    quest = load_quest_file(filepath)

    try:
        stage_number = int(arguments['STAGE'])
    except TypeError:
        stage_number = 0

    stage = quest.stage(stage_number)

    tmpfile = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md')

    if stage.text:
        with tmpfile:
            tmpfile.write(stage.text)
    
    editor = os.environ.get('EDITOR', 'vim')

    result = subprocess.run([
        editor, tmpfile.name
    ])

    if result.returncode != 0:
        sys.exit(1)

    with open(tmpfile.name) as f:
        text = f.read().strip()
    
    if text == '':
        print("No changes were made. Exiting...")

        os.unlink(tmpfile.name)

        sys.exit(0)

    if stage.finishes:
        date_closed = str(date.today())
    else:
        date_closed = None

    payload = {
        'quest': {
            'name': quest.name,
            'slug': arguments['KEY'].replace('/', '_'),
            'date_closed': date_closed,
        },
        'stage': stage_number,
        'text': text,
    }

    url = '{}/quests/journal/'.format(config.url)

    r = requests.post(url, json=payload, auth=HTTPBasicAuth(config.user, config.password))

    if r.ok:
        print(journal_template_from_payload(r.json(), config, JOURNAL_TEMPLATE))

        os.unlink(tmpfile.name)
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))
        
        print("The temporary file was saved at {}".format(
            tmpfile.name
        ))

        sys.exit(1)

    for reward in stage.rewards:
        reward_payload = {
            'reward': reward,
            'rewarded_for': text,
        }

        url = '{}/rewards/claim/'.format(config.url)

        ra = requests.post(url, json=reward_payload, auth=HTTPBasicAuth(config.user, config.password))
        
        if ra.ok:
            print(reward_template_from_payload(ra.json(), config))
        else:
            try:
                print(json.dumps(ra.json(), indent=4, sort_keys=True))
            except json.decoder.JSONDecodeError:
                print("HTTP {}\n{}".format(ra.status_code, ra.text))
            
            print("The temporary file was saved at {}".format(
                tmpfile.name
            ))

    print(journal_template_from_payload(r.json(), config, FINISH_TEMPLATE))



        
            

            
