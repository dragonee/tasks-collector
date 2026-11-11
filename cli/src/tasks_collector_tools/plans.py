from dataclasses import dataclass, field
from datetime import date

import requests
from requests.exceptions import RequestException

from .utils import SHORT_TIMEOUT

FOCUS_TEMPLATE = "Focus: {focus}"

PLAN_TEMPLATE = """
{focus}
"""


def anchored(text, task):
    """``text`` as a line of ``task``: it ends with the task's anchor, which
    is how the server knows which task a line is about whatever it says. A
    plain line of a plan has no task yet, and no anchor."""
    anchor = task.get("anchor")
    return f"{text} ^t{anchor}" if anchor else text


def task_line(task, anchors=False):
    """A task as a checkbox line: ``[ ]`` open, ``[x]`` done, ``[~]`` /
    ``[^]`` done and marked better / best."""
    box = (task.get("mark") or "x") if task["done"] else " "
    text = anchored(task["text"], task) if anchors else task["text"]
    return f"- [{box}] {text}"


@dataclass
class Plan:
    """A single plan section (Daily / Weekly / Big-picture) for the journal
    template. ``tasks`` is what the backend says of each line of the plan:
    ``{"text", "done", "mark", "anchor", ...}``. ``done`` is the task's own,
    whichever plan it is read from."""

    pub_date: str
    thread: str
    tasks: list = field(default_factory=list)

    def render(self, anchors=False):
        """The plan as checkbox lines. With ``anchors`` each task's line ends
        with its anchor, for text that is sent back (the journal template):
        ticking such a line completes that task."""
        if not self.tasks:
            return ""

        lines = "\n".join(task_line(task, anchors) for task in self.tasks)

        focus = FOCUS_TEMPLATE.format(focus="\n" + lines)

        return PLAN_TEMPLATE.format(focus=focus).strip() + "\n"

    def __str__(self):
        return self.render()


def _plan_from_payload(payload):
    return Plan(
        pub_date=payload["pub_date"],
        thread=payload["thread"],
        tasks=payload.get("tasks", []),
    )


def _empty_plans():
    today = date.today().isoformat()
    return {
        "daily": Plan(pub_date=today, thread="Daily"),
        "weekly": Plan(pub_date=today, thread="Weekly"),
        "monthly": Plan(pub_date=today, thread="big-picture"),
    }


def get_plans_for_today_sync(config):
    """Fetch the Daily / Weekly / Big-picture plans for today in a single call,
    each task with whether it is done and the anchor that names it.

    Returns empty plans on any connection/HTTP error so the journal still opens
    offline.
    """
    try:
        url = "{}/api/v1/plans/today/?date={}".format(
            config.url, date.today().isoformat()
        )

        response = requests.get(
            url,
            auth=(config.user, config.password),
            timeout=SHORT_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        return {
            "daily": _plan_from_payload(data["daily"]),
            "weekly": _plan_from_payload(data["weekly"]),
            "monthly": _plan_from_payload(data["monthly"]),
        }
    except RequestException:
        return _empty_plans()


def get_plan_for_today(config):
    """Return just today's Daily plan (with crossed-off flags), for the
    interactive `tasks` command."""
    return get_plans_for_today_sync(config)["daily"]
