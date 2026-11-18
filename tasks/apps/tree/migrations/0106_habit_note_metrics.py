"""Habit notes get their numbers written the one way the code will read them.

Years of hand-written habit notes carry measurements in prose: "#health 7000
kroków", "#health 120/80", "#siłka 15km / 2h 30m", "#spent 45zł". The phones
and tc wrote theirs as tokens, in forms that drifted ("time=22m30s",
"duration=45 min"). From here on a note's metrics are tokens only:

    key=<number><unit>      weight=92.3kg  distance=7.5km  steps=7000
    key=<m>m<s>s            duration=22m30s  duration=45m  (a duration)
    key=<upper>/<lower>     pressure=120/80                (blood pressure)

and a money metric's unit is its currency: amount=90EUR.

Every number of every note was put in a bucket (a metric, a value with no
token form yet: a place, a time of day, a pace; text: part of a URL, a name
like The5, a year; or unknown), with rules that depend on the habit: kilograms
are body weight on health and a load lifted on workout. A note gets its
metrics as tokens after the prose, in parentheses ("#health 7000 kroków
(steps=7000)"); a token in an older form is rewritten where it stands
("time=22m30s" becomes "duration=22m30s"). A note with tokens is read from
them alone, which is how the code will read it.

A note that names one metric twice ("5km rowing, 5km running") was settled
by hand in FIXES, by entry id, guarded by a digest of the note. Body weight
written under health before there was a weight habit moves to it.

What it changed is kept in a table of its own, tree_habittracked_before_0106,
and reversing it puts every entry back as it was: its note, its habit, its
home stream and the same membership row. An entry changed since is left as
it is. See docs/design/habit-metrics.md.
"""

import hashlib
import re
from collections import Counter
from dataclasses import dataclass

from django.db import migrations

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

# The form the code will read: key=<number><unit>, nothing between; for a
# duration key=<minutes>m<seconds>s (seconds left out when there are none);
# for blood pressure key=<upper>/<lower>.
VALUE = (
    r"(?:(\d+)m(?:(\d+)s)?(?!\w)"
    r"|(\d+)/(\d+)(?![\d/])"
    r"|(-?\d+(?:\.\d+)?)([A-Za-z%]*))"
)
TOKEN = re.compile(r"(?<![\w=])([a-z][a-z_]*)=" + VALUE)

# Each metric and the unit it is in. "s" is a duration in seconds, written as
# minutes and seconds; "mmHg" a pair, upper and lower, written without it.
METRICS = {
    "weight": "kg",
    "steps": "",
    "distance": "km",
    "duration": "s",
    "active": "min",
    "kcal": "",
    "pressure": "mmHg",
    "pushups": "",
    "load": "kg",
    "speed": "kmh",
    "amount": "PLN",  # money: the currency it was paid in, PLN, EUR, USD, KZT
    "beers": "",
    "days": "",
    "mood": "",
    "protein": "g",
    "pages": "",
    "words": "",
    "pomodoros": "",
}

# Numbers that measure nothing. Places (location), times of day (wake,
# clock) and paces have no token form yet.
TEXT = "text"


def digest(note):
    """What a fix knows of the note it was written for: the note itself is
    someone's own, and the repository is public."""
    return hashlib.sha256(note.encode()).hexdigest()[:16]


def append(tokens):
    """A fix that writes down which values a note means."""
    return lambda note: f"{note} ({tokens})"


def replace(old, new):
    return lambda note: note.replace(old, new, 1)


def the_last_reading(note):
    """A fix that keeps the last blood pressure reading of a note with
    several, read from the note: a reading has no place in the code."""
    last = re.findall(r"\d{2,3}/\d{2,3}", note)[-1]
    return f"{note} (pressure={last})"


# Notes put right by hand before they are read: entry id -> (digest of the
# note as it is, the fix). A fix that appends tokens settles a conflict, since
# a note with tokens is read from them alone. One whose note has changed
# since is ignored.
FIXES = {
    # A typo: ran 2.5 km.
    4797: ("4b61939aced71588", replace("2.5kg", "2.5km")),
    # Two blood pressure readings one after the other: the second.
    3527: ("911b5f638b4f9630", the_last_reading),
    4052: ("23ec19f82ff70f17", the_last_reading),
    # The minutes were for the first 5 km of 7.5.
    4164: ("ea738558c16bcbe3", append("distance=7.5km")),
    # Two exercises: the heaviest single weight.
    5635: ("08005bb6e2f50ac4", append("load=32kg")),
    8526: ("6038f099cd50473b", append("load=16kg")),
    # Two kinds of cardio: together.
    6974: ("75ffa8a59baee4f2", append("distance=10km")),
    8955: ("f0780481f14984e5", append("duration=20m load=50kg")),
    # The total, not the share of one.
    7632: ("17e57e4e4c4e4811", append("amount=17200PLN")),
}


def fmt(value):
    if isinstance(value, tuple):
        return "/".join(fmt(part) for part in value)
    value = round(float(value), 2)
    return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0")


@dataclass(frozen=True)
class Value:
    key: str
    # a number; (upper, lower) for blood pressure; "7:30" for a time of day;
    # the text for text
    value: object
    unit: str = ""

    @property
    def token(self):
        if self.unit == "s":
            minutes, seconds = divmod(round(self.value), 60)
            return f"{self.key}={minutes}m" + (f"{seconds}s" if seconds else "")
        if isinstance(self.value, tuple):
            return f"{self.key}={fmt(self.value)}"
        return f"{self.key}={fmt(self.value)}{self.unit}"

    @property
    def written(self):
        return (self.key, fmt(self.value), self.unit)


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern
    read: object  # (match) -> [Value], or None to pass the match on
    habits: frozenset = frozenset()  # the habit slugs it reads; empty for all
    machine: bool = False  # a key=value token already: rewritten in place


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    rule: Rule
    values: tuple


@dataclass(frozen=True)
class Reading:
    note: str
    findings: tuple
    unknown: tuple  # (start, end) of each number no rule took


def number(text):
    return float(re.sub(r"\s", "", text).replace(",", "."))


def one(key, unit="", group=1, scale=1, low=None, high=None):
    def read(match):
        value = number(match.group(group)) * scale
        if (low is not None and value < low) or (high is not None and value > high):
            return None
        return [Value(key, value, unit)]

    return read


def literal(key):
    return lambda match: [Value(key, match.group(0))]


def read_token(match):
    """(key, value, unit) of a TOKEN match: a duration in seconds, unit "s";
    a pressure (upper, lower), unit "mmHg"."""
    key, minutes, seconds, upper, lower, value, unit = match.groups()
    if minutes is not None:
        return key, int(minutes) * 60 + int(seconds or 0), "s"
    if upper is not None:
        return key, (int(upper), int(lower)), "mmHg"
    return key, float(value), unit


def token(match):
    return [Value(*read_token(match))]


def minutes_seconds(match):
    return [Value("duration", int(match.group(1)) * 60 + int(match.group(2)), "s")]


def hours_minutes(match):
    minutes = int(match.group(1)) * 60 + int(match.group(2))
    return [Value("duration", minutes * 60, "s")]


def steps(match):
    return [Value("steps", number(match.group(1)) * (1000 if match.group(2) else 1))]


CURRENCIES = {"zł": "PLN", "zl": "PLN", "pln": "PLN", "eur": "EUR", "kzt": "KZT"}
CURRENCIES |= {"usd": "USD", "$": "USD"}


def amount(match):
    return [Value("amount", number(match.group(1)), CURRENCIES[match.group(2).lower()])]


def dollars(match):
    return [Value("amount", number(match.group(1)), "USD")]


def pressure(match):
    upper, lower = int(match.group(1)), int(match.group(2))
    if not (80 <= upper <= 220 and 40 <= lower <= 140 and upper > lower):
        return None
    return [Value("pressure", (upper, lower), "mmHg")]


def pomodoros(match):
    return [Value("pomodoros", number(match.group(1) or match.group(2)))]


WAKING = re.compile(r"pobud|wsta[łjnw]|budzę|budzimy|obudzi|na nogach", re.I)


def time_of_day(match, hour, minute):
    if hour > 23:
        return None
    around = match.string[max(0, match.start() - 30) : match.end() + 15]
    key = "wake" if WAKING.search(around) else "clock"
    return [Value(key, f"{hour}:{minute:02d}")]


def clock(match):
    return time_of_day(match, int(match.group(1)), int(match.group(2)))


def hour(match):
    return time_of_day(match, int(match.group(1)), 0)


def pace(match):
    return [Value("pace", f"{int(match.group(1))}:{match.group(2)}")]


def only(*slugs):
    return frozenset(slugs)


BODY = only("health", "weight", "breakthrough")
TRAINING = only("health", "workout", "breakthrough")
TIMED = only("health", "workout", "sprzatanie", "presence")
MONEY = only("spent", "food")  # money in breakthrough is put aside, not spent
DAY = only(
    "samopoczucie", "workout", "jestem", "presence", "spotkania", "sprzatanie", "food"
)

N = r"(\d+(?:[.,]\d+)?)"
FREE = r"(?<![\d.,\-])"  # not the tail of a bigger number or of a range

# In order: an earlier rule's match takes the numbers in it.
RULES = (
    Rule("url", re.compile(r"https?://\S+"), literal(TEXT)),
    # Tokens the phones and tc write, in older forms first.
    Rule("time=", re.compile(r"\btime=(\d+)m(\d+)s\b"), minutes_seconds, machine=True),
    Rule(
        "duration= min",
        re.compile(r"\bduration=" + N + r"\s?min\b"),
        one("duration", "s", scale=60),
        machine=True,
    ),
    Rule(
        "key=value",
        re.compile(r"(?<![\w=])(" + "|".join(METRICS) + r")=" + VALUE),
        token,
        machine=True,
    ),
    Rule(
        "lat/lng", re.compile(r"\b(?:lat|lng|acc)=-?\d+(?:\.\d+)?"), literal("location")
    ),
    Rule(
        "lat,lng",
        re.compile(r"(?<![\d.])-?\d{1,3}\.\d+\s*,\s*-?\d{1,3}\.\d+"),
        literal("location"),
        only("poi"),
    ),
    # Prose.
    Rule(
        "steps",
        re.compile(FREE + r">?" + N + r"(k)?\s*(?:kroków|kroki|steps)\b", re.I),
        steps,
    ),
    Rule(
        "pushups",
        re.compile(FREE + r"(\d+)\s*(?:pompek|pompki|pompkami)\b", re.I),
        one("pushups"),
    ),
    Rule(
        "amount",
        re.compile(
            FREE
            + r"(\d{1,3}(?:\s\d{3})+|\d+(?:[.,]\d+)?)\s?(zł|zl|PLN|EUR|KZT|USD|\$)(?!\w)",
            re.I,
        ),
        amount,
        MONEY,
    ),
    Rule("$amount", re.compile(r"\$(\d+(?:[.,]\d+)?)(?![\d\w])"), dollars, MONEY),
    Rule(
        "amount, no currency",
        re.compile(r"^[#!]\S+\s+(?:[–-]\s*)?(\d+(?:[.,]\d+)?)(?=\s|$)"),
        one("amount", "PLN"),
        only("spent"),
    ),
    Rule(
        "blood pressure",
        re.compile(r"(?<![\d.,/])(\d{2,3})/(\d{2,3})(?![\d/])"),
        pressure,
        only("health"),
    ),
    Rule(
        "body weight",
        re.compile(r"(?<![\d.,x])" + N + r"\s?kg\b", re.I),
        one("weight", "kg", low=40, high=250),
        BODY,
    ),
    Rule(
        "body weight, bare",
        re.compile(r"^\s*" + N + r"\s*$"),
        one("weight", "kg", low=40, high=250),
        only("weight"),
    ),
    Rule(
        "load",
        re.compile(r"(?<![\d.,])" + N + r"\s?kg\b", re.I),
        one("load", "kg"),
        only("workout"),
    ),
    Rule(
        "speed",
        re.compile(r"(?<![\d.,])" + N + r"\s?km/h", re.I),
        one("speed", "kmh"),
        only("workout"),
    ),
    Rule(
        "distance",
        re.compile(
            r"(?<![\d.,])" + N + r"\s?(?:km|kilometrów|kilometry|kilometr)\b(?!/)", re.I
        ),
        one("distance", "km"),
        TRAINING,
    ),
    Rule(
        "pace", re.compile(r"(\d{1,2}):(\d{2})\s+na\s+km", re.I), pace, only("workout")
    ),
    Rule(
        "hours and minutes",
        re.compile(r"(?<![\d.,x])(\d+)\s?h\s?(\d+)\s?m(?:in)?\b", re.I),
        hours_minutes,
        TIMED,
    ),
    Rule(
        "hours",
        re.compile(r"(?<![\d.,x])" + N + r"\s?h\b", re.I),
        one("duration", "s", scale=3600),
        TIMED,
    ),
    Rule(
        "minutes",
        re.compile(r"(?<![\d.,])(\d+)\s?min(?:ut)?\b", re.I),
        one("duration", "s", scale=60),
        TIMED,
    ),
    Rule(
        "mood",
        re.compile(r"(?<![\d/])(\d{1,2})/10\b"),
        one("mood", high=10),
        only("samopoczucie"),
    ),
    Rule(
        "beers",
        re.compile(FREE + r"(\d+)\s?(?:piwa|piwo|piw)\b", re.I),
        one("beers"),
        only("alkohol"),
    ),
    Rule(
        "beers, after",
        re.compile(r"\bpiwa\s(\d+)\b(?!%)", re.I),
        one("beers"),
        only("alkohol"),
    ),
    Rule(
        "days", re.compile(FREE + r"(\d+)\s?dni\b", re.I), one("days"), only("alkohol")
    ),
    Rule(
        "days without",
        re.compile(FREE + r"(\d+)\s?dni\s+bez\b", re.I),
        one("days"),
        only("breakthrough"),
    ),
    Rule(
        "protein",
        re.compile(FREE + N + r"\s?g\b", re.I),
        one("protein", "g", high=100),
        only("food"),
    ),
    Rule(
        "pages",
        re.compile(FREE + r"(\d+)\s?(?:stron|stronie|strony)\b", re.I),
        one("pages"),
        only("book"),
    ),
    Rule(
        "words", re.compile(FREE + r"(\d+)\s?słów", re.I), one("words"), only("pisanie")
    ),
    Rule(
        "pomodoros",
        re.compile(r"\bx(\d+)\b|(?<![\d.,])(\d+)\s?pomodoro", re.I),
        pomodoros,
        only("sprzatanie"),
    ),
    Rule(
        "time of day",
        re.compile(r"(?<![\d.:])([01]?\d|2[0-3]):([0-5]\d)(?!\d)"),
        clock,
        DAY,
    ),
    Rule(
        "hour",
        re.compile(
            r"\b(?:o|po|do|od|przed|koło|na|pobudka|wstawanie)\s+(\d{1,2})\b"
            r"(?![.,:/]\d)"
            r"(?!\s*(?:min|kg|km|h\b|%|dni|piw|stron|słów|pomodoro|tygodni|weeks"
            r"|osob|rund|x\b))",
            re.I,
        ),
        hour,
        DAY,
    ),
    # Numbers that measure nothing: names (The5, SWY30, S05E03, Django-4.2,
    # 4Developers) and years.
    Rule(
        "name",
        re.compile(
            r"(?<=[A-WYZa-wyz])\d+(?:\.\d+)*"
            r"|(?<=[A-Za-z]-)\d+(?:\.\d+)*"
            r"|(?<![\w.,])\d+(?=[A-Z])"
        ),
        literal(TEXT),
    ),
    Rule("year", re.compile(r"\b(?:19|20)\d{2}\b"), literal(TEXT)),
)


def fixed(pk, note):
    """The note to read for entry ``pk``: its fix, if it still says what the
    fix was written for."""
    if pk not in FIXES:
        return note
    written_for, fix = FIXES[pk]
    return fix(note) if digest(note) == written_for else note


def read_note(note, habit):
    """Each number of ``note`` (of the habit with slug ``habit``) in a bucket."""
    findings = []
    for rule in RULES:
        if rule.habits and habit not in rule.habits:
            continue
        for match in rule.pattern.finditer(note):
            start, end = match.span()
            if any(start < f.end and f.start < end for f in findings):
                continue
            values = rule.read(match)
            if values:
                findings.append(Finding(start, end, rule, tuple(values)))

    findings.sort(key=lambda f: f.start)
    unknown = tuple(
        match.span()
        for match in NUMBER.finditer(note)
        if not any(f.start <= match.start() < f.end for f in findings)
    )
    return Reading(note, tuple(findings), unknown)


def _metrics(reading):
    """The metric values of ``reading``, split into tokens already in the note
    and values read from prose. A note with tokens is read from them alone,
    as the code will read it: they were written by a phone, by tc, by hand (a
    fix), or by an earlier run of ``enhance``."""
    tokens, prose = [], []
    for finding in reading.findings:
        values = [value for value in finding.values if value.key in METRICS]
        if values:
            (tokens if finding.rule.machine else prose).append((finding, values))
    return tokens, [] if tokens else prose


def metric_values(reading):
    tokens, prose = _metrics(reading)
    return [value for _, values in tokens + prose for value in values]


def destination(habit, reading):
    """The habit an entry belongs in: body weight written under health, before
    there was a weight habit, moves to weight."""
    if habit == "health" and {v.key for v in metric_values(reading)} == {"weight"}:
        return "weight"
    return habit


def conflicts(reading):
    """The metrics ``reading`` has more than one value for."""
    counts = Counter(value.key for value in metric_values(reading))
    return sorted(key for key, count in counts.items() if count > 1)


def tokens_in(text):
    """What the code will read from ``text``: its key=<number><unit> metrics."""
    found = (read_token(match) for match in TOKEN.finditer(text))
    return sorted(
        (key, fmt(value), unit) for key, value, unit in found if key in METRICS
    )


def enhance(reading):
    """The note with each of its metrics written as key=<number><unit>, or the
    note as it is when it has conflicts."""
    if conflicts(reading):
        return reading.note

    tokens, prose = _metrics(reading)
    note = reading.note
    for finding, values in sorted(tokens, key=lambda fv: fv[0].start, reverse=True):
        old = note[finding.start : finding.end]
        if tokens_in(old) != sorted(value.written for value in values):
            new = " ".join(value.token for value in values)
            note = note[: finding.start] + new + note[finding.end :]

    appended = [value.token for _, values in prose for value in values]
    if appended:
        note = f"{note.rstrip()} ({' '.join(appended)})"
    return note


# What the migration changed, kept so that reversing it puts every entry back
# as it was. A table of its own, not a model: it goes with a later migration
# once the new notes are settled.
CHANGED = "tree_habittracked_before_0106"


def write_metrics(apps, schema_editor):
    Event = apps.get_model("tree", "Event")
    EventStreamEntry = apps.get_model("tree", "EventStreamEntry")
    Habit = apps.get_model("tree", "Habit")
    HabitTracked = apps.get_model("tree", "HabitTracked")

    schema_editor.execute(
        f"CREATE TABLE {CHANGED} ("
        "event_id integer PRIMARY KEY,"
        " note_before text NOT NULL, note_after text NOT NULL,"
        " habit_before integer NOT NULL, habit_after integer NOT NULL,"
        " stream_before uuid NOT NULL, stream_after uuid NOT NULL)"
    )

    weight_habits = {habit.user_id: habit for habit in Habit.objects.filter(slug="weight")}
    entries = HabitTracked.objects.filter(note__regex=r"[0-9]").select_related("habit")
    changed = []
    for entry in entries.iterator():
        slug = entry.habit.slug
        reading = read_note(fixed(entry.pk, entry.note), slug)
        note = enhance(reading)

        habit = entry.habit
        target = weight_habits.get(habit.user_id)
        if (
            destination(slug, reading) == "weight"
            and target is not None
            and not EventStreamEntry.objects.filter(
                event_id=entry.pk, stream_id=target.event_stream_id
            ).exists()
        ):
            habit = target

        if note == entry.note and habit == entry.habit:
            continue
        changed.append(
            (
                entry.pk,
                entry.note,
                note,
                entry.habit_id,
                habit.pk,
                entry.event_stream_id,
                habit.event_stream_id,
            )
        )

        HabitTracked.objects.filter(pk=entry.pk).update(note=note, habit=habit)
        if habit != entry.habit:
            # Its home stream is its habit's. Historical models don't run
            # Event.save, which keeps the home membership: the membership row
            # moves along, so that reversing puts back the same row.
            Event.objects.filter(pk=entry.pk).update(
                event_stream_id=habit.event_stream_id
            )
            EventStreamEntry.objects.filter(
                event_id=entry.pk, stream_id=entry.event_stream_id
            ).update(stream_id=habit.event_stream_id)

    with schema_editor.connection.cursor() as cursor:
        cursor.executemany(
            f"INSERT INTO {CHANGED} VALUES (%s, %s, %s, %s, %s, %s, %s)", changed
        )


def put_back(apps, schema_editor):
    """Every entry the migration changed, as it was before. An entry changed
    since is left as it is."""
    Event = apps.get_model("tree", "Event")
    EventStreamEntry = apps.get_model("tree", "EventStreamEntry")
    HabitTracked = apps.get_model("tree", "HabitTracked")

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [CHANGED])
        if cursor.fetchone()[0] is None:
            return
        cursor.execute(
            "SELECT event_id, note_before, note_after, habit_before, habit_after,"
            f" stream_before, stream_after FROM {CHANGED}"
        )
        rows = cursor.fetchall()

    for pk, note_before, note_after, habit_before, habit_after, before, after in rows:
        HabitTracked.objects.filter(pk=pk, note=note_after).update(note=note_before)
        if habit_before != habit_after and HabitTracked.objects.filter(
            pk=pk, habit_id=habit_after
        ).update(habit_id=habit_before):
            Event.objects.filter(pk=pk, event_stream_id=after).update(
                event_stream_id=before
            )
            EventStreamEntry.objects.filter(event_id=pk, stream_id=after).update(
                stream_id=before
            )

    schema_editor.execute(f"DROP TABLE {CHANGED}")


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0105_board_thread_required"),
    ]

    operations = [
        migrations.RunPython(write_metrics, put_back),
    ]
