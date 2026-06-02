"""Reflect on a day, week or month.

Usage: 
    reflect [options]

Options:
    -d, --date DATE  Use this date for reflection.
    -w, --week       Use this week for reflection.
    -m, --month      Use this month for reflection.
    -y, --yesterday  Use yesterday for reflection.
    -M, --missing    Fill in missing journal entries for the date range.
    -h, --help       Show this message.
    --version        Show version information.
"""

TEMPLATE = """
> Thread: {thread}
> Published: {published}
> Tags: {tags}
{notes}
{plan}
# Comment

{comment}

"""

GOTOURL = """
See more:
- {url}/
"""

import os, re, sys

from docopt import docopt

from datetime import datetime, date, timedelta

import tempfile

import subprocess

from .config.tasks import TasksConfigFile

from .utils import get_cursor_position

from datetime import timezone

from dateutil.parser import parse

import calendar

def get_start_and_end_of_week(date):
    # Calculate start of week (Monday) and end of week (Sunday) using timedelta
    start = date - timedelta(days=date.weekday())
    end = start + timedelta(days=6)
    return start, end


def get_start_and_end_of_month(date):
    return date.replace(day=1), date.replace(day=calendar.monthrange(date.year, date.month)[1])

def get_fetch_thread_from_arguments(arguments):
    if arguments['--month']:
        return 'Weekly'
    else:
        return None


def get_save_thread_from_arguments(arguments):
    if arguments['--month']:
        return 'big-picture'
    elif arguments['--week']:
        return 'Weekly'
    else:
        return None


def template_from_arguments(arguments):
    cmd = ['reflectiondump']

    day = parse(arguments['--date']) if arguments['--date'] else date.today()

    thread = get_fetch_thread_from_arguments(arguments)

    if thread is not None:
        cmd += ['--thread', thread]

    if arguments['--week']:
        start, end = get_start_and_end_of_week(day)

    elif arguments['--month']:
        start, end = get_start_and_end_of_month(day)

        cmd += [
            '--skip-journals',
        ]
    elif arguments['--yesterday']:
        start = end = day - timedelta(days=1)
    else:
        start = end = day

    cmd += [
        '-d', start.strftime('%Y-%m-%d'),
        '-D', end.strftime('%Y-%m-%d'),
    ]

    return subprocess.check_output(cmd).decode('utf-8').strip().replace('\r', '')


def template_from_payload(payload):
    payload = payload.copy()

    payload['tags'] = ', '.join(payload['tags'])

    return TEMPLATE.format(notes='', plan='', **payload).lstrip()


point_re = re.compile(r'^\s*\-\s*\[([x\^\~])\]\s*')
multi_line_re = re.compile(r'\n(\s*\n)+')

JOURNAL_TEMPLATE = """
{payload}
"""

def journal_payload_from_reflection_payload(payload, published, thread):
    comment = JOURNAL_TEMPLATE.format(payload=payload).strip()
    comment = multi_line_re.sub('\n\n', comment)

    return {
        'published': published.isoformat(),
        'comment': comment,
        'thread': thread,
        'tags': [],
        'reflection': True,
    }


def published_from_arguments(arguments):
    dt = datetime.now()

    if arguments['--date']:
        dt = parse(arguments['--date'])
    
    if arguments['--yesterday']:
        return datetime.now() - timedelta(days=1)
    elif arguments['--week']:
        _, end = get_start_and_end_of_week(dt)
        
        return end.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=timezone.utc)
    elif arguments['--month']:
        _, end = get_start_and_end_of_month(dt)

        return end.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=timezone.utc)
    
    return dt


def fill_missing_journal_entries(arguments):
    """Fill in missing journal entries for the specified date range."""
    cmd = ['reflectiondump', '-M']

    day = parse(arguments['--date']) if arguments['--date'] else date.today()

    thread = get_fetch_thread_from_arguments(arguments)
    if thread is not None:
        cmd += ['--thread', thread]

    if arguments['--week']:
        start, end = get_start_and_end_of_week(day)
    elif arguments['--month']:
        start, end = get_start_and_end_of_month(day)
    elif arguments['--yesterday']:
        start = end = day - timedelta(days=1)
    else:
        start = end = day

    cmd += [
        '-d', start.strftime('%Y-%m-%d'),
        '-D', end.strftime('%Y-%m-%d'),
    ]

    try:
        output = subprocess.check_output(cmd).decode('utf-8').strip()
        
        if not output:
            return
        
        missing_dates = map(lambda x: x.strip(), output.split('\n'))
        
        today = date.today()
        
        def is_past_or_today(date_str):
            try:
                parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                return parsed_date <= today
            except ValueError:
                return False
        
        missing_dates_until_today = list(filter(is_past_or_today, missing_dates))
        
        if not missing_dates_until_today:
            print("No missing journal entries found for past dates.")
            return
            
        print(f"Found {len(missing_dates_until_today)} missing journal entries for past dates.")
        
        for date_str in missing_dates_until_today:
            date_str_formatted = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d (%A)')
            print(f"Creating journal entry for {date_str_formatted}...")

            journal_cmd = ['journal', '--date', date_str]
            
            try:
                subprocess.run(journal_cmd, check=True)
            except subprocess.CalledProcessError:
                print(f"Error creating journal entry for {date_str}")
    except subprocess.CalledProcessError as e:
        print(f"Error running reflectiondump: {e}")


def is_daily_mode(arguments):
    return not arguments['--week'] and not arguments['--month']


def daily_reflection(arguments):
    """Dump quoted journal entries straight into `journal` — no editor opened here."""
    day = parse(arguments['--date']).date() if arguments['--date'] else date.today()

    if arguments['--yesterday']:
        day = day - timedelta(days=1)

    cmd = [
        'reflectiondump',
        '--no-summary',
        '--no-titles',
        '--no-habits',
        '--no-observations',
        '--prefix', '> ',
        '-d', day.strftime('%Y-%m-%d'),
        '-D', day.strftime('%Y-%m-%d'),
    ]

    output = subprocess.check_output(cmd).decode('utf-8').strip().replace('\r', '')

    published = published_from_arguments(arguments)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md') as f:
        f.write(output)
        f.flush()

        journal_cmd = ['journal', '--date', published.isoformat(), '--file', f.name]

        subprocess.run(journal_cmd, check=True)


def get_journal_command_arguments_from_payload(payload):
    """Convert a reflection payload into journal command arguments."""
    cmd = ['journal']

    if 'thread' in payload:
        cmd.extend(['--thread', payload['thread']])
    
    if 'published' in payload:
        cmd.extend(['--date', payload['published']])

    if 'tags' in payload and payload['tags']:
        cmd.extend(['--tags', ', '.join(payload['tags'])])

    return cmd


def main():
    arguments = docopt(__doc__, version='1.1')

    config = TasksConfigFile()
    
    if arguments['--missing']:
        fill_missing_journal_entries(arguments)

    if is_daily_mode(arguments):
        daily_reflection(arguments)
        return

    tmpfile = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md')

    template = template_from_arguments(arguments)

    cursor_position = get_cursor_position(template, "# Reflection")

    with tmpfile:
        tmpfile.write(template)
    
    editor = os.environ.get('EDITOR', 'vim')

    result = subprocess.run([
        editor, f'+{cursor_position}', tmpfile.name,
    ])

    if result.returncode != 0:
        sys.exit(1)

    payload = ''

    with open(tmpfile.name) as f:
        for line in f:
            if line.strip() == '# Journals':
                break

            m = point_re.match(line.strip())
            if not m:
                continue

            # Remove # or ! from the beginning of the text after the checkbox
            cleaned_line = re.sub(r'(\[[x\^\~]\]\s*)([#!])', r'\1', line.strip())
            payload += cleaned_line + '\n'

    os.unlink(tmpfile.name)

    if not payload:
        print("No changes were made to the Comment field.")

        sys.exit(0)

    published = published_from_arguments(arguments)

    thread = get_save_thread_from_arguments(arguments)

    payload = journal_payload_from_reflection_payload(payload, published, thread)

    cmd = get_journal_command_arguments_from_payload(payload)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md') as f:
        f.write(payload['comment'])
        f.flush()

        cmd.extend(['--file', f.name])

        print(cmd)

        subprocess.run(cmd, check=True)

