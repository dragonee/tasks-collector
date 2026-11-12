"""Add journal entry.

The template lists today's plans above the comment. Tick a task there to
complete it: [x], or [~] / [^] for better / best. The ^t... that ends its
line says which task it is, so the line can be reworded; keep the ^t...

Without an editor (a script, an assistant): --no-edit -f FILE sends FILE as
the comment, and --dry-run shows what the server would make of it first.
An entry is sent with a key of its own, so one queued and sent again after
a failed connection is added once.
"""

TEMPLATE = """
> Thread: {thread}
> Published: {published}
> Tags: {tags}
{story}

{plans}

# Comment

{comment}

"""

GOTOURL = """
See more:
- {url}/
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dateutil.parser import parse
from requests.exceptions import ConnectionError

from .config.tasks import TasksConfigFile
from .plans import get_plans_for_today_sync
from .story import get_active_story, get_current_trip, get_story
from .utils import (
    command_parser,
    get_cursor_position,
    local_time,
    queue_failed_request,
    retry_failed_requests,
    sanitize_fields,
    sanitize_list_of_strings,
    smart_open,
    tc_command,
)


def yesterdays_date():
    """Returns yesterday's date at 23:XX."""

    return (datetime.now() - timedelta(days=1)).replace(hour=23)


def get_date_from_arguments(arguments):
    """When the entry was written, with the offset it was written at."""
    if arguments.date:
        return local_time(parse(arguments.date))
    elif arguments.yesterday:
        return local_time(yesterdays_date())

    return local_time(datetime.now())


def format_published(dt):
    return dt.isoformat(sep=" ", timespec="seconds")


def format_plan(plan, title):
    """Format a single plan with its title, only if it has content. Its
    lines carry the tasks' anchors: one ticked in the editor is sent back
    (see ``ticked_in_plans``)."""
    plan_str = plan.render(anchors=True).strip()
    if not plan_str:
        return ""
    return f"# {title}\n{plan_str}\n"


def story_meta_line(story):
    """Render the editable `> Story:` meta line, or '' when there's no story.

    `story` is a dict like {'id': 42, 'title': 'My Trip'} or None.
    """
    if not story:
        return ""
    title = story.get("title")
    if title:
        return f"> Story: {story['id']} ({title})\n"
    return f"> Story: {story['id']}\n"


def template_from_arguments(arguments, plans, comment="", story=None):
    # Format each plan section
    plan_sections = []

    daily_plan = format_plan(plans["daily"], "Daily Plan")
    if daily_plan:
        plan_sections.append(daily_plan)

    weekly_plan = format_plan(plans["weekly"], "Weekly Plan")
    if weekly_plan:
        plan_sections.append(weekly_plan)

    monthly_plan = format_plan(plans["monthly"], "Monthly Plan")
    if monthly_plan:
        plan_sections.append(monthly_plan)

    # Join all non-empty plan sections with newlines
    plans_text = "\n".join(plan_sections)

    return TEMPLATE.format(
        tags=arguments.tags or "",
        comment=comment,
        published=format_published(get_date_from_arguments(arguments)),
        thread=arguments.thread,
        plans=plans_text,
        story=story_meta_line(story),
    ).lstrip()


def template_from_payload(payload):
    payload = payload.copy()

    payload["tags"] = ", ".join(payload["tags"])

    # `story` is write-only on the API, so the response never carries it.
    return TEMPLATE.format(plans="", story="", **payload).lstrip()


title_re = re.compile(r"^# (Comment)")
meta_re = re.compile(r"^> (Thread|Published|Tags|Story): (.*)$")

# A line of a plan section, ticked, with the anchor of its task.
ticked_re = re.compile(r"^\s*-\s*\[[x~^]\]\s*\S.*\s\^t([0-9a-f]{8})\s*$")


def ticked_in_plans(lines, plans):
    """The task lines ticked in the plan sections of the template: those of
    ``lines`` (what the edited file has above ``# Comment``) that are ticked
    now and whose task was not done when the template was made.

    They are sent as part of the comment, where a ticked line that ends with
    a task's anchor completes that task.
    """
    done_already = {
        task["anchor"]
        for plan in plans.values()
        for task in plan.tasks
        if task.get("anchor") and task["done"]
    }
    return [
        line.strip()
        for line in lines
        if (m := ticked_re.match(line)) and m.group(1) not in done_already
    ]


def with_ticked_lines(comment, ticked):
    """``comment`` with the ``ticked`` task lines before it."""
    return "\n".join([*ticked, comment]).strip() if ticked else comment


def add_meta_to_payload(payload, name, item):
    name = name.lower()

    if name == "tags":
        item = item.split(",")
    elif name == "story":
        # Keep only the leading integer id; the optional "(title)" suffix is
        # for the human writer. A blank/non-numeric value means "no story".
        m = re.match(r"^\s*(\d+)", item)
        item = int(m.group(1)) if m else None
    elif name == "published":
        # A time written in without an offset is local, as the one the
        # template came with.
        try:
            item = format_published(local_time(parse(item)))
        except ValueError, OverflowError:
            pass  # sent as it is: the server says what is wrong with it

    payload[name] = item


def add_stack_to_payload(payload, name, lines):
    payload[name.lower()] = "".join(lines).strip()


def list_todays_journals(arguments):
    """List journals from today using `tc reflect dump`."""
    cmd = tc_command("reflect", "dump", "-d", datetime.now().strftime("%Y-%m-%d"))
    if arguments.thread:
        cmd.extend(["--thread", arguments.thread])
    try:
        output = subprocess.check_output(cmd).decode("utf-8").strip()
        print(output)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running tc reflect dump: {e}")
        sys.exit(1)


def resolve_story_from_arguments(arguments, config):
    """Resolve the story to pre-fill into the template, or None.

    Priority: `--story ID` (explicit) > `--current-trip` (saved by the `trip`
    command) > `--active-story` (newest active story from the backend). The
    id is looked up so the meta line can show the title; if the lookup fails
    we fall back to an id-only dict so the link still works offline.
    """
    if arguments.story:
        try:
            story_id = int(arguments.story)
        except ValueError:
            print(f"Ignoring invalid --story value: {arguments.story}")
            return None
        return get_story(config, story_id) or {"id": story_id}

    if arguments.current_trip:
        story_id = get_current_trip()
        if story_id is None:
            print("No current trip set. Use the `trip` command to choose one.")
            return None
        return get_story(config, story_id) or {"id": story_id}

    if arguments.active_story:
        story = get_active_story(config)
        if story is None:
            print("No active story found.")
        return story

    return None


def parse_arguments(argv, prog):
    parser = command_parser(prog, __doc__)

    parser.add_argument("-d", "--date", help="Use this date for the journal entry.")
    parser.add_argument("-T", "--tags", help="Add these tags to the journal entry.")
    parser.add_argument(
        "-Y",
        "--yesterday",
        action="store_true",
        help="Use yesterday's date for the journal entry.",
    )
    parser.add_argument(
        "-t", "--thread", default="Daily", help="Use this thread [default: Daily]."
    )
    parser.add_argument(
        "-S", "--story", metavar="ID", help="Attach this journal entry to story ID."
    )
    parser.add_argument(
        "--active-story",
        action="store_true",
        help="Attach to the currently active story (overridden by --story).",
    )
    parser.add_argument(
        "--current-trip",
        action="store_true",
        help="Attach to the saved current trip (see the `trip` command).",
    )
    parser.add_argument(
        "-f",
        "--file",
        help="Start the comment with this file (- for standard input).",
    )
    parser.add_argument(
        "-F",
        "--force",
        action="store_true",
        help="Send even if content is unchanged from template.",
    )
    parser.add_argument(
        "--no-edit",
        action="store_true",
        help="Don't open the editor: send the comment from -f as it is.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what sending would do (reflection lines, habits, tasks"
        " completed), and send nothing.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --dry-run, print the server's answer as JSON.",
    )
    parser.add_argument(
        "-L", "--today", action="store_true", help="List journals from today."
    )

    arguments = parser.parse_args(argv)

    if arguments.no_edit and not arguments.file:
        parser.error("--no-edit needs -f FILE (or -f - for standard input)")

    return arguments


def describe_preview(preview):
    """What ``--dry-run`` prints: what the entry would do, as the server says."""

    def line(item):
        anchor = f" ^t{item['anchor']}" if item.get("anchor") else ""
        return f"    - {item['text']}{anchor}"

    reflection = preview["reflection"]
    out = [f"{preview['thread']}, published {preview['published']}", ""]

    fields = [field for field in ("good", "better", "best") if reflection[field]]
    if fields:
        out.append(f"Reflection of {reflection['date']}:")
        for field in fields:
            out.append(f"  {field}:")
            out.extend(line(item) for item in reflection[field])
    else:
        out.append("No reflection lines.")

    if preview["habits"]:
        out.append("Habits:")
        for habit in preview["habits"]:
            done = "" if habit["occured"] else "not "
            note = f": {habit['note']}" if habit["note"] else ""
            out.append(f"  - {done}{habit['habit']}{note}")

    if preview["tasks_completed"]:
        out.append("Tasks completed:")
        out.extend(line(item) for item in preview["tasks_completed"])

    if preview["unscheduled_tasks_ticked"]:
        out.append("Ticked on the board:")
        out.extend(f"    - {text}" for text in preview["unscheduled_tasks_ticked"])

    out.extend(["", "Nothing was sent."])
    return "\n".join(out)


def print_error(r):
    try:
        print(json.dumps(r.json(), indent=4, sort_keys=True), file=sys.stderr)
    except json.decoder.JSONDecodeError:
        print("HTTP {}\n{}".format(r.status_code, r.text), file=sys.stderr)


def preview_entry(config, payload, as_json=False):
    """Ask the server what sending ``payload`` would do, and print it."""
    url = f"{config.url}/api/v1/journal/preview/"
    payload = {k: v for k, v in payload.items() if k != "idempotency_key"}

    try:
        r = requests.post(url, json=payload, auth=config.auth)
    except ConnectionError:
        print("Error: Connection failed.", file=sys.stderr)
        sys.exit(2)

    if r.status_code == 404:
        print("Error: the server can't preview entries: it is older than this tc.")
        sys.exit(2)

    if not r.ok:
        print_error(r)
        sys.exit(1)

    if as_json:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    else:
        print(describe_preview(r.json()))


def parse_template(content, payload):
    """Fill ``payload`` from the template as it was saved; returns the lines
    above "# Comment" (the plan sections)."""
    above_comment = []
    current_name = None
    current_stack = []

    for line in content.splitlines(keepends=True):
        if m := meta_re.match(line):
            add_meta_to_payload(payload, m.group(1).strip(), m.group(2).strip())
        elif m := title_re.match(line):
            if current_name is not None:
                add_stack_to_payload(payload, current_name, current_stack)
            else:
                above_comment = current_stack

            current_name = m.group(1).strip()
            current_stack = []
        else:
            current_stack.append(line)

    if current_name is not None:
        add_stack_to_payload(payload, current_name, current_stack)

    return above_comment


def main(argv, prog):
    arguments = parse_arguments(argv, prog)

    config = TasksConfigFile()

    if arguments.today:
        list_todays_journals(arguments)
        return

    plans = get_plans_for_today_sync(config)

    story = resolve_story_from_arguments(arguments, config)

    comment = ""

    if arguments.file:
        with smart_open(arguments.file) as f:
            comment = f.read()

    template = template_from_arguments(arguments, plans, comment, story=story)

    # The file the editor saved; with --no-edit there is none, and the
    # template is sent as it was made.
    tmpname = None

    if arguments.no_edit:
        edited_content = template
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".md"
        ) as tmpfile:
            tmpfile.write(template)
        tmpname = tmpfile.name

        editor = os.environ.get("EDITOR", "vim")

        cursor_position = get_cursor_position(template, "# Comment")
        result = subprocess.run([editor, f"+{cursor_position}", tmpname])

        if result.returncode != 0:
            sys.exit(1)

        # Check if content is empty or unchanged from template
        with open(tmpname) as f:
            edited_content = f.read()

        if not edited_content.strip() or (
            edited_content.strip() == template.strip()
            and not arguments.force
            and not arguments.dry_run
        ):
            print("No changes were made.")
            os.unlink(tmpname)
            sys.exit(0)

    payload = {
        "comment": None,
        "thread": arguments.thread,
        "published": format_published(local_time(datetime.now())),
    }

    above_comment = parse_template(edited_content, payload)

    payload["comment"] = with_ticked_lines(
        payload["comment"] or "", ticked_in_plans(above_comment, plans)
    )

    payload = sanitize_fields(
        payload,
        {
            "tags": sanitize_list_of_strings,
            "story": lambda v: v,  # already an int (or None); not a string to strip
        },
    )

    if not payload["comment"]:
        print("No changes were made to the Comment field.")

        if tmpname:
            os.unlink(tmpname)

        sys.exit(1 if arguments.no_edit else 0)

    if arguments.dry_run:
        preview_entry(config, payload, as_json=arguments.json)
        if tmpname:
            print(f"The entry is in {tmpname}.")
        return

    # Sent again with the entry when it is queued and retried, so the server
    # adds it once.
    payload["idempotency_key"] = uuid.uuid4().hex

    try:
        retry_failed_requests(metadata={"auth": config.auth})
    except Exception as e:
        print(e)
        print("Error: Failed to send queue")

    url = "{}/journal/".format(config.url)

    try:
        r = requests.post(url, json=payload, auth=config.auth)

    except ConnectionError:
        name = queue_failed_request(
            payload,
            metadata={
                "url": url,
            },
            file_type="journal",
        )

        print("Error: Connection failed.")
        print(f"Your update was saved at {name}.")
        print("It will be sent next time you run this program.")

        sys.exit(2)

    if r.ok:
        new_payload = r.json()

        print(template_from_payload(new_payload))

        print(GOTOURL.format(url=config.url).strip())

        if tmpname:
            os.unlink(tmpname)
    else:
        print_error(r)

        if tmpname:
            print("The temporary file was saved at {}".format(tmpname))
        else:
            # A script needs to know; `tc reflect`, which runs the editor,
            # goes on either way.
            sys.exit(1)


def trip_main(argv, prog):
    """Entry point for `tc trip journal`: journal into the current trip."""
    main(["--current-trip", *argv], prog)
