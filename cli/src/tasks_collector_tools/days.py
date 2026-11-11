"""The days of a thread, from the server: each day's events, plan and
reflection, as `api/events/daily/` gives one.

A span is fetched in one request per year (`api/events/`); a server older
than that endpoint is asked a day at a time.
"""

from datetime import timedelta

import requests
from requests.exceptions import RequestException

# The longest span the server answers at once.
MAX_DAYS = 366


class OlderServer(Exception):
    """The server has no `api/events/`."""


def spans(start, end, length=MAX_DAYS):
    """``start`` .. ``end`` as consecutive spans of at most ``length`` days."""
    while start <= end:
        last = min(end, start + timedelta(days=length - 1))
        yield start, last
        start = last + timedelta(days=1)


def _params(thread, anchors):
    params = {"thread": thread or "Daily"}
    if anchors:
        params["anchors"] = "1"
    return params


def _get(config, path, params):
    r = requests.get(f"{config.url}{path}", params=params, auth=config.auth)

    if r.status_code == 404 and path == "/api/events/":
        raise OlderServer()

    try:
        out = r.json()
    except ValueError:
        # An error page (a proxy's 502), not the API's answer.
        out = r.reason

    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {out}")

    return out


def get_day(config, day, thread=None, anchors=False):
    """One day, as the server gives it."""
    return _get(
        config,
        "/api/events/daily/",
        {"date": day.isoformat(), **_params(thread, anchors)},
    )


def get_days(config, start, end, thread=None, anchors=False):
    """The days ``start`` .. ``end`` that have something on them, as the
    server gives them, in order."""
    days = []
    try:
        for first, last in spans(start, end):
            answer = _get(
                config,
                "/api/events/",
                {
                    "from": first.isoformat(),
                    "to": last.isoformat(),
                    **_params(thread, anchors),
                },
            )
            days.extend(answer["days"])
    except OlderServer:
        return _day_by_day(config, start, end, thread, anchors)

    return days


def _day_by_day(config, start, end, thread, anchors):
    """As ``get_days``, a request a day. A day that can't be fetched stops
    it, as a failed span does: left out, it would read as a day with
    nothing on it."""
    days = []
    day = start
    while day <= end:
        try:
            days.append(get_day(config, day, thread, anchors))
        except (RequestException, RuntimeError) as e:
            raise RuntimeError(f"{day}: {e}") from e
        day += timedelta(days=1)
    return days
