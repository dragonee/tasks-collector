"""Each habit declares the metrics its notes carry, and every entry gets the
values they give.

A key a habit's notes write as a token becomes one of its metrics. Its form
says the kind: <m>m<s>s a duration, <upper>/<lower> blood pressure, a number
with a currency (three capitals) money, any other a number in the unit most
of them are written in, with as many decimals as the most precise one. The
lat= and lng= of a point of interest are a place, not a metric. Every weight
habit (built in) records weight in kg, whether or not its notes have any.

Reversing takes the metrics away and empties the values.
"""

import re
from collections import Counter, defaultdict

from django.db import migrations

# The grammar as it was when this ran (services.habits.metrics).
TOKEN = re.compile(
    r"(?:^|(?<=[\s(,;]))([a-z][a-z_]*)="
    r"(?:(\d+)m(?:(\d+)s)?|(\d+)/(\d+)|(-?\d+(?:\.\d+)?)([A-Za-z%]*))"
    r"(?=$|[\s,;.)])"
)
CURRENCY = re.compile(r"[A-Z]{3}")
PLACE = {"lat", "lng", "acc"}


def tokens(note):
    for match in TOKEN.finditer(note or ""):
        key, minutes, seconds, upper, lower, number, unit = match.groups()
        if minutes is not None:
            yield key, "duration", int(minutes) * 60 + int(seconds or 0), "", ""
        elif upper is not None:
            yield key, "pressure", [int(upper), int(lower)], "", ""
        else:
            value = float(number)
            value = int(value) if value.is_integer() else value
            yield key, "number", value, unit, number


def declared(forms):
    """(kind, unit, decimals) of a key from the forms its tokens take, or None
    when they disagree."""
    kinds = {form for form, _, _ in forms}
    if kinds == {"duration"}:
        return "duration", "", 0
    if kinds == {"pressure"}:
        return "pressure", "", 0
    if kinds != {"number"}:
        return None
    units = Counter(unit for _, unit, _ in forms)
    if all(CURRENCY.fullmatch(unit) for unit in units):
        return "money", "", 0
    decimals = max(len(text.partition(".")[2]) for _, _, text in forms)
    return "number", units.most_common(1)[0][0], min(decimals, 2)


def value(metric, form, found, unit):
    if metric.kind == "number" and form == "number" and unit == metric.unit:
        return found
    if metric.kind in ("duration", "pressure") and form == metric.kind:
        return found
    if metric.kind == "money" and form == "number" and CURRENCY.fullmatch(unit):
        return {"amount": found, "currency": unit}
    return None


def declare_metrics(apps, schema_editor):
    Habit = apps.get_model("tree", "Habit")
    HabitMetric = apps.get_model("tree", "HabitMetric")
    HabitTracked = apps.get_model("tree", "HabitTracked")

    entries = HabitTracked.objects.filter(note__contains="=").only(
        "habit_id", "note"
    )
    forms = defaultdict(lambda: defaultdict(list))
    for entry in entries.iterator():
        for key, form, _, unit, text in tokens(entry.note):
            if key not in PLACE:
                forms[entry.habit_id][key].append((form, unit, text))

    for habit_id, keys in forms.items():
        by_count = sorted(keys.items(), key=lambda item: -len(item[1]))
        for order, (key, key_forms) in enumerate(by_count):
            kind = declared(key_forms)
            if kind is not None:
                HabitMetric.objects.create(
                    habit_id=habit_id,
                    key=key,
                    label=key.replace("_", " ").capitalize(),
                    kind=kind[0],
                    unit=kind[1],
                    decimals=kind[2],
                    order=order,
                )

    for habit in Habit.objects.filter(slug="weight"):
        HabitMetric.objects.get_or_create(
            habit=habit,
            key="weight",
            defaults={"label": "Weight", "kind": "number", "unit": "kg", "decimals": 1},
        )

    metrics = defaultdict(dict)
    for metric in HabitMetric.objects.all():
        metrics[metric.habit_id][metric.key] = metric

    for entry in entries.iterator():
        by_key = metrics.get(entry.habit_id)
        if not by_key:
            continue
        values = {}
        for key, form, found, unit, _ in tokens(entry.note):
            if key in by_key and key not in values:
                read = value(by_key[key], form, found, unit)
                if read is not None:
                    values[key] = read
        if values:
            HabitTracked.objects.filter(pk=entry.pk).update(values=values)


def take_back(apps, schema_editor):
    apps.get_model("tree", "HabitMetric").objects.all().delete()
    apps.get_model("tree", "HabitTracked").objects.exclude(values={}).update(
        values={}
    )


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0107_habit_metrics"),
    ]

    operations = [
        migrations.RunPython(declare_metrics, take_back),
    ]
