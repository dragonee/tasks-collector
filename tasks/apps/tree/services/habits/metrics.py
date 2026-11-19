"""A habit's metrics, read from its notes and written into them.

A note's metrics are tokens (docs/design/habit-metrics.md):

    key=<number><unit>      weight=80.5kg  steps=7000      a number
    key=<m>m<s>s            duration=22m30s  duration=45m  a duration
    key=<upper>/<lower>     pressure=120/80                blood pressure
    key=<number><currency>  amount=90EUR                   money

A token stands on its own: at the start of the note or after a space, "(",
"," or ";", and before the end or a space or ",;.)". The note is what is
kept; ``HabitTracked.values`` is what its habit's metrics read from it.

A value as stored: a number as is, a duration in seconds, blood pressure as
``[upper, lower]``, money as ``{"amount": 90, "currency": "EUR"}``.
"""

import re
from collections import Counter, namedtuple

from django.core.exceptions import ValidationError

TOKEN = re.compile(
    r"(?:^|(?<=[\s(,;]))([a-z][a-z_]*)="
    r"(?:(\d+)m(?:(\d+)s)?|(\d+)/(\d+)|(-?\d+(?:\.\d+)?)([A-Za-z%]*))"
    r"(?=$|[\s,;.)])"
)

CURRENCY = re.compile(r"[A-Z]{3}")

NUMBER = "number"
DURATION = "duration"
PRESSURE = "pressure"
MONEY = "money"


def tokens(note):
    """(key, form, value, unit) of each token of ``note``, in order: form is
    number, duration (value in seconds) or pressure (value (upper, lower))."""
    found = []
    for match in TOKEN.finditer(note or ""):
        key, minutes, seconds, upper, lower, number, unit = match.groups()
        if minutes is not None:
            found.append((key, DURATION, int(minutes) * 60 + int(seconds or 0), ""))
        elif upper is not None:
            found.append((key, PRESSURE, (int(upper), int(lower)), ""))
        else:
            found.append((key, NUMBER, _number(number), unit))
    return found


def _number(text):
    value = float(text)
    return int(value) if value.is_integer() else value


def _value(metric, form, value, unit):
    """The value a token gives ``metric``, or None when its form doesn't fit."""
    if metric.kind == NUMBER and form == NUMBER and unit == metric.unit:
        return value
    if metric.kind == DURATION and form == DURATION:
        return value
    if metric.kind == PRESSURE and form == PRESSURE:
        return list(value)
    if metric.kind == MONEY and form == NUMBER and CURRENCY.fullmatch(unit):
        return {"amount": value, "currency": unit}
    return None


def read(note, metrics):
    """The values ``note`` gives ``metrics``, by key: the first fitting token
    of each."""
    by_key = {metric.key: metric for metric in metrics}
    values = {}
    for key, form, value, unit in tokens(note):
        if key in by_key and key not in values:
            found = _value(by_key[key], form, value, unit)
            if found is not None:
                values[key] = found
    return values


def _fmt(number, decimals=2):
    text = f"{round(float(number), decimals):.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def token(metric, value):
    """``value`` (as stored) of ``metric``, written as its token."""
    if metric.kind == DURATION:
        minutes, seconds = divmod(int(value), 60)
        return f"{metric.key}={minutes}m" + (f"{seconds}s" if seconds else "")
    if metric.kind == PRESSURE:
        return f"{metric.key}={value[0]}/{value[1]}"
    if metric.kind == MONEY:
        return f"{metric.key}={_fmt(value['amount'])}{value['currency']}"
    return f"{metric.key}={_fmt(value, metric.decimals)}{metric.unit}"


def clean(metric, raw):
    """A value of ``metric`` sent by a client, as stored. Raises
    ValidationError for one that doesn't fit its kind."""
    try:
        if metric.kind == DURATION:
            seconds = int(raw)
            if seconds < 0 or seconds != raw:
                raise ValueError
            return seconds
        if metric.kind == PRESSURE:
            upper, lower = (int(part) for part in raw)
            if not (0 < lower < upper) or [upper, lower] != list(raw):
                raise ValueError
            return [upper, lower]
        if metric.kind == MONEY:
            amount, currency = raw["amount"], raw["currency"]
            if not CURRENCY.fullmatch(currency):
                raise ValueError
            return {"amount": _number(_fmt(float(amount))), "currency": currency}
        if isinstance(raw, bool):
            raise ValueError
        return _number(_fmt(float(raw), metric.decimals))
    except TypeError, ValueError, KeyError:
        raise ValidationError(_EXPECTED[metric.kind])


_EXPECTED = {
    NUMBER: "A number.",
    DURATION: "A whole number of seconds.",
    PRESSURE: "Two whole numbers, upper and lower: [120, 80].",
    MONEY: 'An amount and a currency: {"amount": 90, "currency": "EUR"}.',
}


def without(note, keys):
    """``note`` without its tokens for ``keys``."""
    if not keys:
        return note

    def drop(match):
        return "" if match.group(1) in keys else match.group(0)

    note = TOKEN.sub(drop, note)
    note = re.sub(r"\(\s*\)", "", note)
    return re.sub(r"\s{2,}", " ", note).strip()


def write(note, metrics, values):
    """``note`` with ``values`` (as stored, by key) written in as tokens, in
    place of any it had for those keys: after the text, in parentheses, or
    alone when there is no text."""
    by_key = {metric.key: metric for metric in metrics}
    note = without((note or "").strip(), set(values))
    written = " ".join(
        token(by_key[key], value) for key, value in values.items() if value is not None
    )
    if not written:
        return note
    return f"{note} ({written})" if note else written


def refresh(habit):
    """Read every entry of ``habit`` again, after its metrics changed."""
    from ...models import HabitTracked

    metrics = list(habit.metrics.all())
    entries = HabitTracked.objects.filter(habit=habit).only("note", "values")
    changed = []
    for entry in entries:
        values = read(entry.note, metrics)
        if values != entry.values:
            entry.values = values
            changed.append(entry)
    HabitTracked.objects.bulk_update(changed, ["values"], batch_size=500)


def latest(habit, key):
    """The newest entry of ``habit`` that has a value for ``key``, or None."""
    from ...models import HabitTracked

    return (
        HabitTracked.objects.filter(habit=habit, occured=True, values__has_key=key)
        .order_by("-published")
        .first()
    )


MetricUse = namedtuple("MetricUse", "metric entries last")


def in_use(user):
    """``user``'s metrics by key, in key order, each with how many entries of
    its habit carry a value for it and when the last of them was published."""
    from ...models import HabitMetric, HabitTracked

    entries, last = Counter(), {}
    rows = (
        HabitTracked.objects.filter(habit__user=user)
        .exclude(values={})
        .values_list("habit_id", "values", "published")
    )
    for habit_id, values, published in rows.iterator():
        for key in values:
            at = (habit_id, key)
            entries[at] += 1
            last[at] = max(published, last.get(at, published))

    by_key = {}
    metrics = (
        HabitMetric.objects.filter(habit__user=user)
        .select_related("habit")
        .order_by("key", "habit__name")
    )
    for metric in metrics:
        at = (metric.habit_id, metric.key)
        by_key.setdefault(metric.key, []).append(
            MetricUse(metric, entries[at], last.get(at))
        )
    return by_key


def shown(metric, value):
    """``value`` (as stored) of ``metric`` for people: 80.5 kg, 1 h 5 min,
    120/80, 90 EUR."""
    if metric.kind == DURATION:
        minutes, seconds = divmod(int(value), 60)
        hours, minutes = divmod(minutes, 60)
        parts = [f"{hours} h"] if hours else []
        if minutes or not (hours or seconds):
            parts.append(f"{minutes} min")
        if seconds:
            parts.append(f"{seconds} s")
        return " ".join(parts)
    if metric.kind == PRESSURE:
        return f"{value[0]}/{value[1]}"
    if metric.kind == MONEY:
        return f"{_fmt(value['amount'])} {value['currency']}"
    return f"{_fmt(value, metric.decimals)} {metric.unit}".strip()
