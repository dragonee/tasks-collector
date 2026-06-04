"""Connect to the Tasks Collector.

Usage:
    tasks [options]

Options:
    --thread THREAD  Use specific thread.
    -h, --help       Show this message.
    --version        Show version information.

By default, tasks are added to the thread from your profile.
By prefixing a line with `!` or `#`, it will be added to the Habit Tracker instead.
"""

GOTOURL = """
See more:
- {url}/todo/#/board/{name}
"""

import json
import shlex
import subprocess
import sys
from collections.abc import Iterable
from difflib import SequenceMatcher

import requests
from docopt import docopt
from more_itertools import consume, repeatfunc
from requests.auth import HTTPBasicAuth

from .config.tasks import TasksConfigFile
from .models import ProfileResponse, StatsResponse

try:
    import atexit
    import os
    import readline

    readline_available = True
except ImportError:
    readline_available = False

import re

from .habits import add_habit
from .plans import get_plan_for_today
from .story import get_active_stories, set_current_trip


def get_input_until(predicate, prompt=None):
    text = None

    while text is None or not predicate(text):
        text = input(prompt)

    return text


HELP = """
Available commands:
{commands}

Quit by pressing Ctrl+D or Ctrl+C.
"""

DEFAULT_THREAD = "Daily"


def load_default_thread_from_profile(config):
    """Load default board thread from user profile API."""
    try:
        url = f"{config.url}/profile/"
        r = requests.get(url, auth=HTTPBasicAuth(config.user, config.password))

        if r.ok:
            profile_response = ProfileResponse.parse_obj(r.json())
            if profile_response.results:
                return profile_response.results[0].default_board_thread.name
    except Exception as e:
        pass

    return DEFAULT_THREAD


def setup_readline_history(config):
    """Set up readline history functionality."""
    if not readline_available:
        return

    # Set history file path
    history_file = os.path.expanduser("~/.tasks_history")

    # Load existing history
    try:
        readline.read_history_file(history_file)
    except FileNotFoundError:
        pass  # No history file exists yet
    except PermissionError:
        pass  # Can't read history file

    # Set maximum history size
    readline.set_history_length(1000)

    # Save history on exit
    def save_history():
        try:
            readline.write_history_file(history_file)
        except PermissionError:
            pass  # Can't write history file

    atexit.register(save_history)


def list_to_points(list):
    return "\n".join([f"  {item}" for item in list])


def help():
    return HELP.format(commands=list_to_points(commands.keys()))


def print_help(*args):
    print(help())


def change_thread(args, config):
    if not args:
        print(f"Current thread: {config.current_thread}")
        return

    new_thread = args[0]
    print(f"Changed thread from '{config.current_thread}' to '{new_thread}'")
    config.current_thread = new_thread


def open_observation(args, config):
    if args:
        subprocess.call(["open", f"{config.url}/observations/{args[0]}"])
    else:
        subprocess.call(["open", f"{config.url}/observations/"])


def show_stats(args, config):
    """Fetch and display statistics from the Tasks Collector."""
    year = args[0] if args else None

    url = f"{config.url}/stats/json/"
    params = {"year": year} if year else {}

    try:
        r = requests.get(
            url, params=params, auth=HTTPBasicAuth(config.user, config.password)
        )

        if r.ok:
            stats = StatsResponse.parse_obj(r.json())

            # Format and print the stats
            year_display = stats.year if stats.year else "All time"
            print(f"\nStatistics for {year_display}")
            print("=" * 50)

            print(f"\nActivity Counts:")
            print(f"  Total Events:                    {stats.event_count:>6}")
            print(f"  Journal Entries:                 {stats.journal_count:>6}")
            print(f"  Habit Trackings:                 {stats.habit_count:>6}")

            print(f"\nObservations:")
            print(f"  Made:                            {stats.observation_count:>6}")
            print(
                f"  Updated:                         {stats.observation_updated_count:>6}"
            )
            print(
                f"  Closed:                          {stats.observation_closed_count:>6}"
            )
            print(
                f"  Recontextualized:                {stats.observation_recontextualized_count:>6}"
            )
            print(
                f"  Reflected Upon:                  {stats.observation_reflected_upon_count:>6}"
            )
            print(
                f"  Reinterpreted:                   {stats.observation_reinterpreted_count:>6}"
            )

            print(f"\nProjected Outcomes:")
            print(
                f"  Made:                            {stats.projected_outcome_made_count:>6}"
            )
            print(
                f"  Redefined:                       {stats.projected_outcome_redefined_count:>6}"
            )
            print(
                f"  Rescheduled:                     {stats.projected_outcome_rescheduled_count:>6}"
            )
            print(
                f"  Closed:                          {stats.projected_outcome_closed_count:>6}"
            )

            print(
                f"\nWord Count:                        {stats.word_count:>6} (last updated: {stats.word_count_updated.strftime('%Y-%m-%d %H:%M:%S')})"
            )

            if stats.years:
                print(f"\nAvailable years: {', '.join(map(str, stats.years))}")
        else:
            print(f"Error fetching stats: HTTP {r.status_code}")
            try:
                print(json.dumps(r.json(), indent=4, sort_keys=True))
            except json.decoder.JSONDecodeError:
                print(r.text)
    except Exception as e:
        print(f"Error fetching stats: {e}", file=sys.stderr)


def select_trip(args, config):
    """Set the current trip, saved to ~/.tasks/current_trip.

    With an id argument, save it directly. Without one, list the active
    trips: auto-select when there's exactly one, otherwise prompt for a
    1-N choice. `tjournal`/`tripjournal` then journal into this trip.
    """
    if args:
        try:
            story_id = int(args[0])
        except ValueError:
            print(f"Invalid trip id: {args[0]}")
            return

        set_current_trip(story_id)
        print(f"Current trip set to #{story_id}.")
        return

    stories = get_active_stories(config)

    if not stories:
        print("No active trips found. Use `trip <id>` to set one explicitly.")
        return

    for i, s in enumerate(stories, 1):
        print(f"  {i}. #{s['id']} {s.get('title') or ''}".rstrip())

    if len(stories) == 1:
        story = stories[0]
    else:
        choice = get_input_until(
            lambda t: t.isdigit() and 1 <= int(t) <= len(stories),
            prompt=f"Pick a trip (1-{len(stories)}): ",
        )
        story = stories[int(choice) - 1]

    set_current_trip(story["id"])
    print(f"Current trip set to #{story['id']} {story.get('title') or ''}".rstrip())


commands = {
    "observation": "observation",
    "olist": ["observation", "-l"],
    "habits": "habits",
    "hlist": ["habits", "-l"],
    "oedit": open_observation,
    "edit": open_observation,
    "quest": "quest",
    "journal": "journal",
    "sjournal": "sjournal",
    "trip": select_trip,
    "tjournal": ["journal", "--current-trip"],
    "tripjournal": ["journal", "--current-trip"],
    "thought": ["journal", "-T", "thoughts"],
    "update": "update",
    "help": print_help,
    "clear": "clear",
    "wtf": ["journal", "-T", "wtf"],
    "nove": ["journal", "-T", "nove"],
    "reflect": "reflect",
    "thread": change_thread,
    "stats": show_stats,
}


def match_text_against_commands(text):
    for command in commands.keys():
        if command.startswith(text):
            return commands[command]

    return None


def run_command(command, args, config):
    if callable(command):
        command(args, config)
        return

    if type(command) == str:
        command = [command]

    if isinstance(command, Iterable):
        try:
            command_list = command + args
            return_code = subprocess.call(command_list)
            if return_code != 0:
                print(f"Command exited with return code {return_code}", file=sys.stderr)

            return
        except Exception as e:
            print(f"Error executing command: {e}", file=sys.stderr)

            return

    raise TypeError(f"Invalid command: {command}")


def is_habit_command(text):
    return text.startswith("!") or text.startswith("#")


def run_single_task(config):
    if config.current_thread != DEFAULT_THREAD:
        original_text = get_input_until(bool, prompt=f"({config.current_thread}) > ")
    else:
        original_text = get_input_until(bool, prompt="> ")

    parts = shlex.split(original_text)

    if is_habit_command(parts[0]):
        add_habit(config, original_text)
        return

    command = match_text_against_commands(parts[0])

    if command is not None:
        run_command(command, parts[1:], config)

        return

    add_task(config, config.current_thread, original_text)


RE_THREAD = re.compile(r"^(.*?)\s*>\s*([A-Za-z0-9_-]+)\s*$")


def add_task(config, default_thread, text):
    match = RE_THREAD.match(text)

    if match:
        text = match.group(1).strip()
        thread = match.group(2).strip()
    else:
        thread = default_thread

    payload = {
        "thread-name": thread,
        "text": text,
    }

    url = "{}/boards/append/".format(config.url)

    r = requests.post(
        url, json=payload, auth=HTTPBasicAuth(config.user, config.password)
    )

    if r.ok:
        print(GOTOURL.format(url=config.url, name=thread).strip())
    else:
        try:
            print(json.dumps(r.json(), indent=4, sort_keys=True))
        except json.decoder.JSONDecodeError:
            print("HTTP {}\n{}".format(r.status_code, r.text))


def main():
    arguments = docopt(__doc__ + help(), version="1.0.2")

    config = TasksConfigFile()

    # Set up readline history
    setup_readline_history(config)

    print("Connected to Tasks Collector at {}".format(config.url))

    plan = get_plan_for_today(config)

    print(plan)

    # Load default thread from profile if not specified via command line
    thread_from_args = arguments["--thread"]
    if thread_from_args:
        config.current_thread = thread_from_args
    else:
        config.current_thread = load_default_thread_from_profile(config)

    try:
        consume(
            repeatfunc(
                run_single_task,
                None,
                config,
            )
        )
    except (KeyboardInterrupt, EOFError):
        print("Exiting...")
