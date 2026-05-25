# Trips on Android (phase 1: text notes + GPS POI)

This note explains the **Trips** feature on the Android companion app —
how the phone starts/stops a trip, how individual notes flow into a
`Story` with linked `JournalAdded` (and any `HabitTracked` extracted
from `#poi`/`#coords` hashtags), and the wire contract that the
backend exposes.

The companion to this doc is `design-tasks-on-android.md` for the
Today flow; the two share the same auth, the same DRF view shape, and
the same Compose architecture, so most of the project conventions
already carry over.

## Why this exists

The Today tab is a per-day surface — its records (Board / Plan /
Reflection) reset every day. A **Trip** is a long-running container
that groups multiple journal-style events under one record with an
explicit start and stop. Underneath, it's a `Story` (the generic name)
of `type='trip'`, with an intermediary table `StoryEvent` linking it
to individual `Event` rows.

Phase 1 ships text notes with automatic GPS-based POI tagging. Phase 2
will add photos (separate doc).

## Endpoints

All six live under `/api/v1/android/trip/...` and use the same auth as
`/api/v1/habit/track/`: DRF `TokenAuthentication` + `IsAuthenticated`,
`@csrf_exempt`, JSON request and response.

| Method | URL                                       | Body / query                                          | Returns                                              |
|--------|-------------------------------------------|-------------------------------------------------------|------------------------------------------------------|
| POST   | `/api/v1/android/trip/start/`             | `{"title"?, "type"? (default "trip")}`                | `{"story": {id, title, started, type, stopped:null}}` |
| POST   | `/api/v1/android/trip/stop/`              | `{"story_id"}`                                        | `{"story": {...}}`                                   |
| POST   | `/api/v1/android/trip/update/`            | `{"story_id", "title"}`                               | `{"story": {...}}`                                   |
| POST   | `/api/v1/android/trip/note/`              | `{"story_id", "comment", "published": ISO 8601}`      | `{"ok": true, "journal_id": <int>}`                  |
| GET    | `/api/v1/android/trip/list/`              | `?page=1&page_size=20`                                | `{"active":[...], "history":[...], "total_history":N, "page":..., "page_size":...}` |
| GET    | `/api/v1/android/trip/<story_id>/`        | —                                                     | `{"story":{...}, "events":[...]}`                    |

Error model: `400` on missing/malformed input, `401` without a valid
token, `404` on story-not-found or not-owned-by-user (one code on
purpose, to avoid leaking existence), `409` on `add_trip_note`
against a stopped story.

### `published` carries a full timestamp (like `/complete`)

Trip notes mirror the Today `/complete` contract: the device sends a
full ISO 8601 timestamp from `OffsetDateTime.now().toString()`. The
server uses that verbatim as `JournalAdded.published`, and any
`HabitTracked` extracted from a `#poi` hashtag carries the same
moment.

## Service module

`tasks/apps/tree/services/trips/` contains everything the backend does
for these endpoints. The views are thin: parse, dispatch, translate
exceptions to HTTP.

```
services/trips/
├── __init__.py        # public surface
├── operations.py      # @transaction.atomic orchestrators
└── titles.py          # default_title(started) -> "Trip YYYY-MM-DD HH:MM"
```

Public operations (each wrapped in `@transaction.atomic`):

- `start_trip(user, title=None, type_='trip', started=None)` — creates
  the `Story`; auto-generates a title via `titles.default_title` when
  blank.
- `stop_trip(user, story_id)` — sets `stopped=now()` once; idempotent.
- `update_trip(user, story_id, title=...)` — rename.
- `add_trip_note(user, story_id, comment, published=None)` — creates
  a `JournalAdded` on the user's `default_board_thread` (Daily
  fallback), then calls `process_journal_entry(journal_added,
  story=story)` so embedded hashtags create `HabitTracked` events
  that are also linked to the story.
- `list_active(user)` / `list_history(user, page, page_size)` /
  `get_detail(user, story_id)`.

Error classes: `StoryNotFoundError`, `StoryStoppedError`.

### "Current story" lookup

Stories are per-user. Threads are global, so the user FK lives on
`Story`. The Android client passes an explicit `story_id` on every
trip-attached event; the backend never infers "current trip"
globally — multiple concurrent active trips are allowed.

### Story↔Event link

```python
class StoryEvent(models.Model):
    story = ForeignKey(Story, related_name='entries')
    event = OneToOneField(Event, related_name='story_entry')
    created_at = auto_now_add
```

The `OneToOneField` to the polymorphic `Event` base enforces "an
event belongs to at most one story" at the DB level. `JournalAdded`
and `HabitTracked` are both polymorphic `Event` subclasses, so a
single FK to `Event` covers both without per-subclass duplication.

## The journal-processing extension

`process_journal_entry(journal_added, skip_habits=False, story=None)`
in `services/journalling/journal_processing.py` accepts an optional
`story=`. When provided:

- the `JournalAdded` itself is linked via `StoryEvent`, and
- every `HabitTracked` extracted from hashtags in the comment is
  linked to the same story.

When `story=None` (every existing caller), behavior is unchanged.

This is the **only** integration point between Trips and journalling —
no parallel POI extractor was built. A trip note containing
`#poi lat=… lng=…` produces both a journal entry and a POI habit
event in the same atomic transaction, with both linked to the trip.

## POI Habit

The Habit + 4 `HabitKeyword` rows (`poi`, `coords`, `coordinates`,
`latlng`) are created by data migration `0068_poi_habit`. The habit is
global (matches existing Habit semantics — Habits are not per-user).
The migration's reverse drops the habit and the keywords.

## Wire format for the prepended POI line

The Android client always prepends a `#poi` line to the user's note
when a GPS fix is available:

```
#poi lat=40.712800 lng=-74.006000
<user's free-form note, multi-line>
```

- `lat`/`lng` are formatted with 6 decimal places using `Locale.US` so
  the decimal separator is always `.` regardless of system locale.
- The existing `parse_habit_tokens` splits the comment on
  whitespace-followed-by `#` or `!`, so the first token (until the
  newline) is `#poi lat=… lng=…`. `match_token_to_habit` matches it
  to the POI Habit and stores `note = '#poi lat=… lng=…'` on the
  resulting `HabitTracked`.

If GPS is missing and the user explicitly enables "send without
location", the comment is sent unmodified — no `#poi` line, no POI
HabitTracked created for that note.

## Dialog flow

```
Trip detail screen
      │
      └── Add note (button)
              │
              ▼
          AddNoteDialog
            │  on open: ask FusedLocationProviderClient for a fresh fix
            │
            ├── GpsState.Waiting   → Send disabled
            ├── GpsState.Ready     → preview "Location ready (lat, lng)"
            │                        Send enabled; prepends "#poi lat=… lng=…"
            ├── GpsState.Denied    → "Grant location permission" button +
            │                        "Send without location" toggle
            └── GpsState.Unavailable → "Send without location" toggle only
```

The dialog's "Send" button is blocked until either (a) GPS resolves to
a fix or (b) the user explicitly opts to send without location.

## Android architecture

Compose UI on top of `kotlinx.coroutines` `StateFlow`s in two
`AndroidViewModel`s.

```
android/app/src/main/java/org/polybrain/tasks/health/
├── data/TasksApi.kt              # Retrofit DTOs + 6 trip endpoints
├── location/LocationProvider.kt  # FusedLocationProvider wrapper (suspend)
├── ui/trip/TripsScreen.kt        # active list, history list, start button
├── ui/trip/TripsViewModel.kt     # active / history / focusTrip flows
├── ui/trip/TripDetailScreen.kt   # event list, add-note + stop buttons
├── ui/trip/TripDetailViewModel.kt# detail / GPS state / send flow
└── ui/trip/AddNoteDialog.kt      # the GPS-gated dialog
```

### Navigation

`MainActivity.kt` `Destination` enum gains a `Trips` entry inserted
between `Today` and `Health`. When `tripDetailId != null`, the Trips
slot renders `TripDetailScreen(storyId = …)`; otherwise it renders
`TripsScreen(onOpenTrip = …)`. `BackHandler` un-sets `tripDetailId` on
system back so the user always returns to the trips list.

### "Where do trips live?" UX

`TripsScreen` behavior:

- **0 active trips, 0 history** → "Start a trip" button only
- **0 active trips, N history** → button + history list
- **1 active trip** → on **first** screen load only, auto-navigate
  to that trip's detail. Subsequent refreshes (e.g., after the user
  pressed back) stay on the list so back-navigation is sticky.
- **2+ active trips** → list of all active (above) + history (below)

### Compose flow inside `TripDetailViewModel`

`AddNoteDialog` observes `gps: StateFlow<GpsState>` and
`allowNoLocation: StateFlow<Boolean>`. Sending fires
`composeComment(fix, text)` which produces either
`"#poi lat=… lng=…\n<note>"` or the bare note depending on whether
a fix is present.

## Tests

- `tasks/apps/tree/tests/test_trip_service.py` — start/stop/rename/note,
  ownership boundary (cross-user → `StoryNotFoundError`), stopped-trip
  rejection, list+pagination, get_detail ordering.
- `tasks/apps/tree/tests/test_trip_api.py` — APITestCase end-to-end
  for all six endpoints, error codes (400/401/404/409), POI hashtag
  auto-link.
- `tasks/apps/tree/tests/test_journal_processing_story.py` — confirms
  `process_journal_entry(…, story=s)` links the JournalAdded and every
  extracted HabitTracked, and that `story=None` preserves the existing
  behavior verbatim.

## Invariants worth preserving

- **`Story.user` is per-user**; the global Thread model gave us no
  natural per-user scope, so it had to live on Story.
- **`StoryEvent.event` is OneToOne**: an event is in at most one
  story. If you ever need many-to-many, drop the unique constraint —
  but consider whether two stories owning the same event makes
  semantic sense first.
- **All writes inside `add_trip_note` share one transaction.** The
  JournalAdded, any HabitTracked, and the StoryEvent rows commit
  together or not at all. Don't split them.
- **POI HabitTracked never goes through `/habit/track/`** for trip
  notes — that endpoint is idempotent on `(habit, date)` which would
  collapse all of a day's POIs into one. Trip POIs always flow
  through `process_journal_entry`, which calls
  `HabitTracked.objects.create` directly.
- **Cross-user story access returns 404, not 403.** Don't change this
  without thinking about what existence-leak it would create.

## Where to start reading

Backend: `services/trips/operations.py` → `services/journalling/journal_processing.py` →
`views_android_trip.py`.

Wire contract: `views_android_trip.py` + `urls.py:android-trip-*`.

Android: `ui/trip/TripsScreen.kt` → `ui/trip/TripDetailScreen.kt` →
`ui/trip/AddNoteDialog.kt` → `location/LocationProvider.kt`.

Tests live in `tasks/apps/tree/tests/test_trip_*.py` and
`test_journal_processing_story.py`.
