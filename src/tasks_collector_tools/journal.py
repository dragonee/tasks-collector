"""Add journal entry.

Usage: 
    journal [options]

Options:
    -d, --date DATE  Use this date for the journal entry.
    -T TAGS, --tags TAGS  Add these tags to the journal entry.
    -s               Also save a copy as new observation, filling Situation field.
    -o               Alias for -s.
    -Y, --yesterday  Use yesterday's date for the journal entry.
    -t THREAD, --thread THREAD  Use this thread [default: Daily]
    -f FILE, --file FILE  Use this file instead of the generated template.
    -F, --force      Send even if content is unchanged from template.
    -L, --today      List journals from today.
    -h, --help       Show this message.
    --version        Show version information.
"""

TEMPLATE = """
> Thread: {thread}
> Published: {published}
> Tags: {tags}
{notes}

{plans}

# Comment

{comment}

"""

GOTOURL = """
See more:
- {url}/
"""

import json, os, re, sys

from docopt import docopt

from datetime import datetime, date, timedelta
from dateutil.parser import parse

import tempfile

import subprocess

import requests
from requests.exceptions import ConnectionError

from requests.auth import HTTPBasicAuth

from pathlib import Path

from .config.tasks import TasksConfigFile

from .quick_notes import get_quick_notes_as_string

from .plans import get_plans_for_today_sync
from .utils import sanitize_fields, get_cursor_position, sanitize_list_of_strings, queue_failed_request, retry_failed_requests

def yesterdays_date():
    """Returns yesterday's date at 23:XX."""

    return (datetime.now() -  timedelta(days=1)).replace(hour=23)


def get_date_from_arguments(arguments):
    if arguments['--date']:
        return parse(arguments['--date'])
    elif arguments['--yesterday']:
        return yesterdays_date()
    
    return datetime.now()   


def format_plan(plan, title):
    """Format a single plan with its title, only if it has content."""
    plan_str = str(plan).strip()
    if not plan_str:
        return ""
    return f"# {title}\n{plan_str}\n"

def template_from_arguments(arguments, quick_notes, plans, comment=''):
    # Format each plan section
    plan_sections = []
    
    daily_plan = format_plan(plans['daily'], "Daily Plan")
    if daily_plan:
        plan_sections.append(daily_plan)
        
    weekly_plan = format_plan(plans['weekly'], "Weekly Plan")
    if weekly_plan:
        plan_sections.append(weekly_plan)
        
    monthly_plan = format_plan(plans['monthly'], "Monthly Plan")
    if monthly_plan:
        plan_sections.append(monthly_plan)
    
    # Join all non-empty plan sections with newlines
    plans_text = "\n".join(plan_sections)
    
    return TEMPLATE.format(
        tags=arguments['--tags'] or '',
        comment=comment,
        published=get_date_from_arguments(arguments),
        thread=arguments['--thread'],
        notes=quick_notes,
        plans=plans_text,
    ).lstrip()


def template_from_payload(payload):
    payload = payload.copy()

    payload['tags'] = ', '.join(payload['tags'])

    return TEMPLATE.format(notes='', plans='', **payload).lstrip()

title_re = re.compile(r'^# (Comment)')
meta_re = re.compile(r'^> (Thread|Published|Tags): (.*)$')


def add_meta_to_payload(payload, name, item):
    if name.lower() == 'tags':
        item = item.split(',')

    payload[name.lower()] = item

def add_stack_to_payload(payload, name, lines):
    payload[name.lower()] = ''.join(lines).strip()






def list_todays_journals(arguments):
    """List journals from today using reflectiondump."""
    cmd = ['reflectiondump', '-d', datetime.now().strftime('%Y-%m-%d')]
    if arguments['--thread']:
        cmd.extend(['--thread', arguments['--thread']])
    try:
        output = subprocess.check_output(cmd).decode('utf-8').strip()
        print(output)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running reflectiondump: {e}")
        sys.exit(1)

def main():
    arguments = docopt(__doc__, version='1.1')

    config = TasksConfigFile()

    if arguments['--today']:
        list_todays_journals(arguments)
        return

    quick_notes = get_quick_notes_as_string(config)
    
    plans = get_plans_for_today_sync(config)

    tmpfile = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md')

    comment = ''

    if arguments['--file']:
        with open(arguments['--file'], 'r') as f:
           comment = f.read()
    
    template = template_from_arguments(arguments, quick_notes, plans, comment)

    cursor_position = get_cursor_position(template, "# Comment")

    with tmpfile:
        tmpfile.write(template)
    
    editor = os.environ.get('EDITOR', 'vim')

    result = subprocess.run([
        editor, f'+{cursor_position}', tmpfile.name,
    ])

    if result.returncode != 0:
        sys.exit(1)

    # Check if content is empty or unchanged from template
    with open(tmpfile.name) as f:
        edited_content = f.read()

    if not edited_content.strip() or (edited_content.strip() == template.strip() and not arguments['--force']):
        print("No changes were made.")
        os.unlink(tmpfile.name)
        sys.exit(0)

    payload = {
        'comment': None,
        'thread': arguments['--thread'],
        'published': datetime.now(),
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

    payload = sanitize_fields(payload, {
        'tags': sanitize_list_of_strings,
    })

    if not payload['comment']:
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

    url = '{}/journal/'.format(config.url)

    try:
        r = requests.post(url, json=payload, auth=HTTPBasicAuth(config.user, config.password))

        if arguments['-s'] or arguments['-o']:
            url = '{}/observation-api/'.format(config.url)

            new_payload = {
                'situation': payload['comment'],
                'thread': arguments['--thread'],
                'pub_date': str(date.today()),
                'type': 'observation',
            }

            r2 = requests.post(url, json=new_payload, auth=HTTPBasicAuth(config.user, config.password))

            if r2.ok:
                print("Saved observation under id {}".format(r2.json()['id']))
            else:
                try:
                    print(json.dumps(r2.json(), indent=4, sort_keys=True))
                except json.decoder.JSONDecodeError:
                    print("HTTP {}\n{}".format(r2.status_code, r2.text))
        

    except ConnectionError:
        name = queue_failed_request(payload, metadata={
            'url': url,
        }, file_type="journal")

        print("Error: Connection failed.")
        print(f"Your update was saved at {name}.")
        print("It will be sent next time you run this program.")

        sys.exit(2)

    if r.ok:
        new_payload = r.json()

        print(template_from_payload(new_payload))

        print(GOTOURL.format(url=config.url).strip())

        os.unlink(tmpfile.name)
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))
        
        print("The temporary file was saved at {}".format(
            tmpfile.name
        ))



        
            

            
