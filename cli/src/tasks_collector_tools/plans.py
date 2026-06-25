from dataclasses import dataclass, field
from datetime import date

import requests
from requests.exceptions import RequestException

from .utils import SHORT_TIMEOUT

FOCUS_TEMPLATE = "Focus: {focus}"

PLAN_TEMPLATE = """
{focus}
"""


@dataclass
class Plan:
    """A single plan section (Daily / Weekly / Big-picture) for the journal
    template. ``tasks`` is the backend-computed list of ``{"text", "done"}``
    items, where ``done`` means the task has been crossed off (the line also
    appears in that day's Reflection.good)."""

    pub_date: str
    thread: str
    tasks: list = field(default_factory=list)

    def __str__(self):
        if not self.tasks:
            return ""

        lines = "\n".join(
            "- [{}] {}".format("x" if task["done"] else " ", task["text"])
            for task in self.tasks
        )

        focus = FOCUS_TEMPLATE.format(focus="\n" + lines)

        return PLAN_TEMPLATE.format(focus=focus).strip() + "\n"


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
        "monthly": Plan(pub_date=today, thread="Big-picture"),
    }


def get_plans_for_today_sync(config):
    """Fetch the Daily / Weekly / Big-picture plans for today in a single call,
    each task already flagged with whether it has been crossed off. The backend
    (reusing the Today service) computes the done state; we just render it.

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
