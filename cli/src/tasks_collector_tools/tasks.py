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
import select
import shlex
import subprocess
import sys
import tempfile
import termios
import tty
from collections.abc import Iterable
from datetime import datetime
from difflib import SequenceMatcher

import requests
from colored import attr, fg
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


def format_focus_elapsed(seconds):
    """Render an elapsed duration as ``XmXs`` (e.g. ``35m20s``)."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs}s"


def read_key_with_timeout(timeout):
    """Return a single keypress from stdin, or None if ``timeout`` seconds
    elapse first. Assumes stdin is already in cbreak mode."""
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return None
    return os.read(sys.stdin.fileno(), 1).decode(errors="ignore")


def run_focus_clock(task_text, config):
    """Show the live focus screen and block until the user closes it.

    The last line ticks once a second in place. Returns one of ``"journal"``
    (j/c, close and journal), ``"record"`` (r, track the habit and stop),
    ``"record_journal"`` (R, seed a journal with just the ``#focus`` line) or
    ``"exit"`` (x/Esc), along with the elapsed seconds. Pressing t drops out
    to capture a task for later and then resumes the same session.
    """
    grey = fg("dark_gray")
    bold = attr("bold")
    reset = attr("reset")

    start = datetime.now()

    print(f"\nFocus mode: {task_text}")
    print(
        f"{grey}j/c) close and journal, r) record habit, R) record and journal, "
        f"t) task for later, x/esc) exit{reset}"
    )

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    result = "exit"
    try:
        tty.setcbreak(fd)

        while True:
            elapsed = (datetime.now() - start).total_seconds()
            timer = format_focus_elapsed(elapsed)
            line = f"{bold}From {start.strftime('%H:%M')}, {timer}{reset}"
            sys.stdout.write(f"\r\033[K{line}")
            sys.stdout.flush()

            key = read_key_with_timeout(1.0)
            if key is None:
                continue
            if key in ("j", "c", "J", "C"):
                result = "journal"
                break
            if key == "r":
                result = "record"
                break
            if key == "R":
                result = "record_journal"
                break
            if key in ("t", "T"):
                add_focus_task(config, fd, old_settings)
                print(f"{grey}Resuming focus: {task_text}{reset}")
                continue
            if key in ("x", "X", "\x1b"):
                result = "exit"
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print()

    elapsed = (datetime.now() - start).total_seconds()
    return result, elapsed


def run_focus_journal(task_text, elapsed, complete=True):
    """Open the journal pre-filled with the focus session for ``task_text``.

    When ``complete`` is true the entry crosses the task off (``- [x] TASK``)
    on top of the ``#focus`` line; otherwise only the ``#focus`` line is
    seeded, leaving the task open.
    """
    timer = format_focus_elapsed(elapsed)
    focus_line = f"#focus time={timer} {task_text}\n"
    if complete:
        content = f"- [x] {task_text}\n{focus_line}"
    else:
        content = focus_line

    tmpfile = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md")
    with tmpfile:
        tmpfile.write(content)

    try:
        subprocess.call(["journal", "-f", tmpfile.name, "-F"])
    finally:
        try:
            os.unlink(tmpfile.name)
        except OSError:
            pass


def record_focus_habit(task_text, elapsed, config):
    """Track the ``#focus`` habit for this session without crossing the task
    off or opening the journal."""
    timer = format_focus_elapsed(elapsed)
    add_habit(config, f"#focus time={timer} {task_text}")


def add_focus_task(config, fd, old_settings):
    """Temporarily leave the focus screen to capture a task for later, then
    return so the timer can keep running. Empty input cancels."""
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    print()
    try:
        text = input("Task for later (empty to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        text = ""

    if text:
        add_task(config, config.current_thread, text)

    tty.setcbreak(fd)


def focus_mode(args, config):
    """Focus timer over a task from today's Daily plan.

    Lists the plan's tasks, lets you pick one, then shows a live-ticking timer.
    Passing text directly (``focus Some task``) skips the picker and focuses on
    that text instead. Press j/c to close the session and open a pre-filled
    journal entry, r to just track the ``#focus`` habit (task stays open), R to
    seed a journal with only the ``#focus`` line, t to capture a task for later
    and keep focusing, or x/Esc to exit back to the normal prompt without
    recording anything.
    """
    if not sys.stdin.isatty():
        print("Focus mode requires an interactive terminal.")
        return

    if args:
        task_text = " ".join(args)
    else:
        plan = get_plan_for_today(config)

        if not plan.tasks:
            print("No tasks in today's plan to focus on.")
            return

        for i, task in enumerate(plan.tasks, 1):
            print(f"  {i}) {task['text']}")

        choice = get_input_until(
            lambda t: t.isdigit() and 1 <= int(t) <= len(plan.tasks),
            prompt=f"Pick a task to focus on (1-{len(plan.tasks)}): ",
        )
        task_text = plan.tasks[int(choice) - 1]["text"]

    result, elapsed = run_focus_clock(task_text, config)

    if result == "journal":
        run_focus_journal(task_text, elapsed)
    elif result == "record":
        record_focus_habit(task_text, elapsed, config)
    elif result == "record_journal":
        run_focus_journal(task_text, elapsed, complete=False)


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
    "focus": focus_mode,
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
