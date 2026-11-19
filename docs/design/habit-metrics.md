# Habit metrics

How the numbers in habit notes are written, what code finds a habit by, and
where an event happened. Current as of 2026-11-18 (migrations through 0112).
"What is next" lists what is planned and not built.

## Roles (0109, 0110)

Code finds a habit by what it is for, never by its slug or a keyword, which are
the user's to change:

| Role | Written by | Read by |
|---|---|---|
| `breakthrough` | the web "+Breakthrough" button (the text is the note) | the Breakthrough page |
| `weight` | the phones' activity dialog, opened from the weight row | `latest_weight`: the Health screens, `api/v1/android/health/data/` |
| `daily-health` | the phones' hourly sync, one entry a day | — |
| `bike-ride` | the phones' sync, one entry a ride | — |

```python
class HabitRole(models.Model):
    user = FK(User)                 # the habit's owner, set on save
    role = CharField(choices=Role)
    habit = FK(Habit, related_name="roles")
    # unique (user, role); one habit may fill several roles

class HabitTracked(Event):
    ...
    role = CharField(blank=True)    # the role it was written for, if any
```

- `services/habits/roles.py` says what each role is: the name, keywords and
  metrics of the habit made for it, and whether it is one entry a day.
  `habit_for(user, role)` reads; `habit_for_writing` writes, and when no habit
  fills the role it makes one from the role (a numbered slug when the user has
  that slug, only the keywords nobody has) and fills it. Writing for a role
  also gives its habit the role's metrics it lacks.
- Writers name a `role` instead of a `keyword`: `api/v1/habit/track/` (the
  day's entry) and `api/v1/habit/tracked/` (a new entry each time).
- One entry a day is the role's own entry of the day: the sync never
  overwrites an entry typed by hand. The role's own keyword counts as the
  role, so phones that still send `health-metrics` get it too; any other
  write of the day (the Today screen's habit dialog) replaces only an entry
  that is no role's.
- New users' built-in weight habit fills `weight`. Habit settings choose the
  habit for each role ("Used for"); one left empty is filled by the next write
  for it. Moving a role leaves past entries where they are. The habit's page
  says which roles it fills; habits carry `roles` in the API.
- `api/v1/android/health/data/` carries `roles`: by role, the name, keyword
  (the role's own when its habit has it) and metrics of the habit a write for
  it goes to (`role_habits`). A role nobody fills says what its first write
  makes, so every role is there. The phones' weight row builds its dialog
  from `roles.weight`, whatever the profile selects, and writes by the role.
- 0110 filled the roles from the habits that played them (slugs `breakthrough`
  and `weight`, the habits of the `health-metrics` and `workout` keywords) and
  marked the entries the phones had written for them. On the production dump:
  5 roles, 200 entries marked. Reversing empties both.
- `focus`, gym and running need no role: tc's focus line is a hashtag the
  journal reads anyway, and the activity dialog lists habits with metrics.

Before roles, writers found a habit by keyword and readers by slug, two
identifiers that only happened to agree; only `poi` and `weight` were
provisioned, so the sync answered 404 for everyone else and retried forever;
the day's entry replaced whichever entry of the habit came first, one typed
by hand included; and a hashtag from code could land on any keyword sharing
three letters (`#breakthrough` on `#breathing`).

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
- Places, times of day and paces have no token: a place is an `EventLocation`
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

## HabitMetric (0107, 0108)

What a habit records with each entry, declared on it:

```python
class HabitMetric(models.Model):
    habit = FK(Habit, related_name="metrics")
    key = CharField()               # the token's key; fixed once entries carry it
    label = CharField()
    kind = CharField()              # number, duration, pressure, money
    unit = CharField(blank=True)    # a number's: kg, km, min; never m or s
    decimals = PositiveSmallIntegerField(default=0)
    order = PositiveSmallIntegerField(default=0)
    # unique (habit, key)

class HabitTracked(Event):
    ...
    values = JSONField(default=dict)    # read from the note on every save
```

- The note is what is kept; `values` is what the habit's metrics read from it
  (`services/habits/metrics.py`), on every save and again for every entry
  when a metric is added or taken away. A value as stored: a number as is, a
  duration in seconds, blood pressure `[upper, lower]`, money
  `{"amount": 90, "currency": "EUR"}`.
- A token stands on its own (after the start, a space, `(`, `,` or `;`; before
  the end, a space or `,;.)`), so `?v=4dSL` in a link is not one. Only the keys
  the habit declares are read, and only in a form that fits the kind.
- `POST api/v1/habit/tracked/` makes a new entry each time, from `keyword`,
  `note`, `values` (by key) and `published`, with an `idempotency_key`; the
  values are written into the note as tokens. `api/v1/habit/track/` (one entry
  a day) takes `values` too. An unknown key or a value that doesn't fit is a
  400.
- Habits come with `metrics` wherever the API sends them;
  `habit/keywords/mine/?with_tracked=true` keeps the habits tracked today.
- The habit's page (`/habits/<slug>/`) is for reading: its metrics with
  their latest values, the calendar and the archive. Metrics are edited on
  the Metrics page (`/metrics/`, in the menu): every metric of the user's
  habits by key, with the habits that record it, how many entries carry a
  value and the last of them, and the form that adds one to a habit
  (`?habit=<slug>` chooses it; the habit's page links there). So does the
  admin.
- The phones' activity dialog (the + button) offers the profile's keywords
  and asks for the chosen habit's metrics by kind (a number, minutes and
  seconds, upper and lower, an amount and a currency); the note is the
  hashtag and what was written. Bike rides from the sync are sent with their `duration` as a value
  (and a key, so a ride sent twice is one entry); tc's focus line writes
  `duration=<m>m<s>s`.
- The built-in weight habit records `weight` in kg; `latest_weight` is the
  latest value of the habit that fills the weight role.
- 0108 declared each habit's metrics from the tokens its notes carry: the form
  gives the kind, the units the unit, the most precise the decimals; `lat` and
  `lng` are a place. On the production dump: 29 metrics, 615 entries with
  values. Reversing takes them away.

## EventLocation (0111, 0112)

Where an event happened, attachable to any event:

```python
class EventLocation(models.Model):
    event = OneToOneField(Event, primary_key=True, related_name="location")
    lat = FloatField()
    lng = FloatField()
    acc = FloatField(null=True)     # metres, when the phone knows
```

- The phones send `lat`, `lng` and `acc` as fields of a trip note, a trip
  photo or a standalone photo; a trip note may be a place alone.
  `services/locations.py` reads them (`place_from`) and attaches them
  (`locate`).
- An older phone writes the place as the comment's first line,
  `#poi lat=… lng=…` (or `#coords`, `#coordinates`, `#latlng`), and its
  outbox may still hold such notes: `split_place` reads the line off and makes
  it the location. That is the one parser of the line left, until no such
  phone is in use. A place is no longer a `poi` habit entry; `#poi` typed in
  the journal is an ordinary hashtag.
- The trip map plots the events that have a location; a journal entry with
  one shows its pin (`journal_added.html`), and `app.js` only points the pin
  at the user's map service. The trip detail API gives each entry its
  `location`, and both apps show it from there.
- 0112 made each comment's place line its location and took the line out of
  the comment: 212 on the production dump, 178 of them a place alone. What it
  changed is kept in `tree_journaladded_before_0112`; reversing puts the lines
  back, except where a comment changed since.

On the production dump, 0106 to 0112 forward, backward, forward and backward
again left every tracked habit, membership, habit and journal comment as it
was, row for row, and both forwards the same.

## What is next

### Drop what 0106 and 0112 kept

`tree_habittracked_before_0106` and `tree_journaladded_before_0112` go with a
later migration, once the new notes are settled. After that, reversing either
changes nothing.

### Deploy the server before the apps

The apps send roles, values and places that only this server takes. Phones
not updated keep working: the server reads their keywords, `#poi` lines and
older tokens.

### Open

- A token form for a time of day, if waking time is worth a chart.
- Buckets for what stayed unknown: sets and repetitions, ranges.
- Which metrics `breakthrough` declares: its notes carry weight, distance and
  days.
- Charts of a metric on the habit's page.
