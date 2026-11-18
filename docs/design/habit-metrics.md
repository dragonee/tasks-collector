# Habit metrics

How the numbers in habit notes are written, and how the habits the code depends
on come apart from it. Current as of 2026-11-18 (migrations through 0106). "What
is next" lists what is planned and not built.

## Habits the code depends on

| Hashtag → habit | Written by | Note | Read by |
|---|---|---|---|
| `#breakthrough` | the web "+Breakthrough" button, prefilled `#breakthrough ` (`app.js`) | free text | the Breakthrough page, by slug `breakthrough` (`views_breakthrough.py`) |
| `#poi` `#coords` `#coordinates` `#latlng` → `poi` (built-in) | the phones, as the first line of a trip note or photo | `lat=… lng=… [acc=…]` | four regexes, one per client: `views_trip.py`, `app.js`, `TripNoteFormat.kt`, `TripNoteFormat.swift` |
| `#weight` → `weight` (built-in) | the Health screens of both apps | `weight=<x>kg` | `services/health`, by slug `weight`, served at `api/v1/android/health/data/` |
| `#health-metrics` | the hourly sync of both apps, through `TrackHabitAPIView` (one entry a day, replaced) | `steps= distance=km active=min kcal=` | nothing |
| `#workout` | bike rides from the sync | `Bike ride (duration=<n> min)` | nothing |
| `#siłka` `#workout` `#running` | the activity dialog, an `ActivityType` enum in both apps | free text; `distance=<x>km, time=<m>m<s>s` for a run | nothing |
| `#focus` | tc focus mode | `time=<m>m<s>s <task>` | nothing |

What ties them to the code:

- Writers find a habit by keyword, readers by slug: two identifiers that only
  happen to agree, both editable. Renaming one empties a page without an error.
- Only `poi` and `weight` are provisioned. For anyone without a
  `health-metrics` keyword the phone sync gets a 404 and retries forever, and
  the bike rides after it in the loop are never sent.
- A hashtag matches the keyword sharing the longest prefix of at least three
  letters (`habit_extraction.py`): `#breakthrough` from the button can land on
  someone's `#breathing`, a bike ride's `#workout` on `#work`.
- Replacing the day's entry belongs to the endpoint, not the habit, and it
  replaces whichever entry of the habit that day comes first, one typed by
  hand included. Weight is a habit of its own only to stay out of its way.

## The note format

A note's metrics are tokens; prose around them is for people.

| Form | Example | Read as |
|---|---|---|
| `key=<number><unit>` | `weight=80.5kg` `distance=7.5km` `steps=7000` `kcal=2000` | a number in that unit |
| `key=<m>m<s>s` | `duration=22m30s` `duration=45m` | a duration, in seconds; seconds left out when there are none |
| `key=<upper>/<lower>` | `pressure=120/80` | blood pressure, a pair in mmHg, written without the unit |
| `key=<number><currency>` | `amount=45PLN` `amount=90EUR` | money: the unit is the currency it was paid in |

- Nothing goes between the key, the number and the unit. A decimal is a dot.
- A note with tokens is read from them alone: "6km (30min na 4km) (distance=6km)"
  has a distance and no duration.
- `active=80min` from the sync stays minutes, as the phones write it.
- Places, times of day and paces have no token: places become `EventLocation`
  (below); a time of day ("pobudka 7:30") and a pace ("7:30 na km") stay prose.

## Migration 0106

Wrote the metrics of every existing note as tokens, so the code that reads them
needs nothing but the format above.

- Every number of every note was put in a bucket: a metric, a value without a
  token (a place, a time of day, a pace), text (part of a URL, a name like
  Team42, a year), or unknown. The rules depend on the habit: kilograms are
  body weight on `health` and a load lifted on `workout`; money counts on
  `spent` and `food`, not in `breakthrough`, where it was put aside.
- Prose gets its tokens after it, in parentheses: "#health 7000 kroków" became
  "#health 7000 kroków (steps=7000)". A token in an older form was rewritten
  where it stood: `time=22m30s` became `duration=22m30s`, `duration=45 min`
  became `duration=45m`.
- A note that names one metric twice was settled by hand: two blood pressure
  readings in a row keep the second; two exercises keep the heaviest weight;
  two kinds of cardio add up; a total beats a share. The fixes are by entry id,
  guarded by a digest of the note, since notes are their writer's own and the
  repository is public. A note changed since is read as it is.
- Body weight written under `health`, from before there was a `weight` habit,
  moved to `weight`: the entry, its home stream and its membership of it.
- What it changed is kept in `tree_habittracked_before_0106`, a table of its
  own. Reversing puts every entry back as it was: note, habit, home stream and
  the same membership row. An entry changed since is left as it is.
- On the production dump of 2026-11-10, migrated from 0076: 394 entries
  changed, 194 of them moved. Forward, backward, forward, backward left every
  tracked habit, membership and habit as it was, row for row, and both
  forwards the same.
- Left unknown: sets and repetitions (`3x63kg`, `x3`), ranges (`15-20k`),
  counts in parentheses, dates. Nothing reads them yet.

## What is next

### Drop what 0106 kept

`tree_habittracked_before_0106` goes with a later migration, once the new
notes are settled. After that, reversing 0106 changes nothing.

### Clients write the format

tc writes `#focus time=…`; the phones write a run's `time=…` and a bike ride's
`duration=<n> min`. All three write `duration=<m>m<s>s` from now on. Until they
do, new notes come in the older forms.

### EventLocation

A location attachable to any event (`lat`, `lng`, `acc`), sent by the phones as
fields of a note or a photo instead of a `#poi lat=… lng=…` line. The trip map,
the pin and both apps read it; the four regexes and the line stripping in
`app.js` go. A migration moves the existing lines (`#poi lat=… lng=…`, and the
older `#poi <lat>,<lng>`) into rows. `#poi` can stay a plain habit.

### HabitMetric

What a habit records, declared on it:

```python
class HabitMetric(models.Model):
    habit = FK(Habit, related_name="metrics")
    key = SlugField()               # the token's key; fixed once values exist
    label = CharField()
    kind = CharField()              # number, duration, pressure, money
    unit = CharField(blank=True)    # kg, km; none for duration, pressure, money
    decimals = PositiveSmallIntegerField(default=0)
    order = PositiveSmallIntegerField(default=0)
    # unique (habit, key)

class HabitTracked(Event):
    ...
    values = JSONField(default=dict)    # {"weight": 80.5}, by HabitMetric.key
```

- Values are read from a note's tokens, for the keys its habit declares, and
  are optional on every entry (a gym visit has no distance).
- The API takes `values` as fields; an unknown key or a wrong kind is a 400.
- The apps' weight and running dialogs become one form, built from the
  habit's metrics and loaded from the server instead of `ActivityType`.
- `latest_weight` becomes the latest value of a metric; any metric can be
  charted.
- A migration declares each habit's metrics from the keys its notes carry and
  fills `values`.

### Roles

Code finds a habit by what it is for, not by its slug or keyword:

| Role | Writes | Reads |
|---|---|---|
| `breakthrough` | the "+Breakthrough" button | the Breakthrough page |
| `weight` | the weight dialog | the Health screen |
| `daily-health` | the hourly sync, one entry a day | — |
| `bike-ride` | the sync, one entry a ride | — |

```python
class HabitRole(models.Model):
    user = FK(User)
    role = CharField(choices=ROLES)   # ROLES in code: name, keywords, metrics
    habit = FK(Habit, related_name="roles")
    # unique (user, role); habit.user == user
```

- One habit may fill several roles.
- Writers send the role instead of a hashtag; hashtags stay for people.
- The first write for a role nobody fills creates the habit from the role
  (name, metrics, keywords that are free) and fills it. That ends the sync's
  404 without giving everyone Health and Workout habits up front. A page
  reading an unfilled role shows its empty state.
- One entry a day replaces the role's own entry for that day, not any entry
  of the habit.
- A migration fills the roles from today's slugs and keywords, and marks the
  past sync entries as the role's. Installed apps keep the keyword paths
  until both send roles.
- Habit settings get "Used for" per role. Moving a role to another habit
  leaves the past entries where they are.
- `focus`, gym and running need no role: tc's focus line is a hashtag the
  journal reads anyway, and the dialog lists habits with metrics.

### Open

- A token form for a time of day, if waking time is worth a chart.
- Buckets for what stayed unknown: sets and repetitions, ranges.
- Which metrics `breakthrough` declares: its notes carry weight, distance and
  days.
