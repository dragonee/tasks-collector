# Multi-user refactor — open bugs and follow-ups

Review of the multi-user work (PRs #338–#347, commits `e7fb720..9ce2317`, merged
2026-11-10/11) against the plan in `multiuser-event-streams.md`. Reviewed at
`9ce2317`.

State at review time: the test suite is green (602 tests), `makemigrations --check`
reports no changes, and every write tried as a stranger or as a viewer of a shared
item was rejected. What follows is what did not hold.

A second pass the same day drove the dev server through its three clients: the web
UI in Chrome, the CLI run from `cli/src`, and the Android app (on the emulator, plus
its API with token auth). It ran as the owner of the production copy, as `tester` (a
user created in the admin) and as a viewer of shared items, and counted SQL queries
on every route. It found item 9, which breaks the observation editor and should be
fixed first, and everything from "New users" on.

How each item was checked is marked:
- **reproduced** — a throwaway test in the dev container showed it;
- **clients** — done through the browser, the CLI or the Android app against the dev
  server;
- **read** — traced in the code, not run;
- **data** — counted on the dev database (a copy of production from 2026-11-11).

## Access problems

### 1. A legacy `Profile.default_board_thread` gives another user's board

- [x] Fixed by shared boards (Stage 8 in `multiuser-event-streams.md`) — reproduced,
  data, clients

Decided: "Razem" is a joint board, and boards can be shared to edit. Migration 0093
turned karolina's pointer into an editor share of "Razem" (and would clear a pointer
at someone else's built-in board; the dev copy has none). `board_thread_for` now
ignores a default board the user can't change, and revoking a board clears it. Checked
on the dev copy: karolina gets "Razem (dragonee)" on the web board, in the Android
board items and as her profile's default; tester gets nothing. In Chrome, tester
shared a board from Account Settings, and django opened it, added a task to it and
reloaded it. Later, django moved an item from his own Daily into it through
"Move to" and a commit. Editors also see the shared board's commits on `/summaries/`,
and deleting an editor keeps their commits (0094). Last, tester shared and stopped
sharing that board from the board page's "Share" control. An unknown username showed
its error there, and typing in the box didn't trigger the board's `i` shortcut.

The same pointer also broke appending without a thread name (Android "add task",
the CLI's default thread): `boards/append/` looked "Razem" up among karolina's own
threads and answered 404. Fixed by the same change.

What follows is the problem as found.

`board_thread_for` (`tasks/apps/tree/board_operations.py:131`) returns the profile's
thread without checking who owns it, and `_current_board`
(`tasks/apps/tree/services/today/operations.py:114`) loads its board with no owner
filter. `ProfileForm` only offers the user's own threads, but no migration reset
values set before threads had owners: 0078 gave every thread to one user and left
other users' profiles pointing at them.

On the dev copy, karolina's profile points at dragonee's "Razem" thread.

What the other user's board is exposed to:
- `GET /api/v1/android/board/items/` returns it;
- `POST /api/v1/android/task/add/`, `task/complete`, `task/delete`, `task/move` change it;
- `POST /journal/` with `[x] <task>` ticks a task on it (`journal_processing.py`,
  `_check_matching_board_tasks`);
- `GET /profile/` shows the thread's id and name.

`boards/append/` is not affected: it looks the thread up by name among the caller's
own threads.

This contradicts the Stage 6 exit ("a second user logs into an empty app").

**Decision needed first:** "Razem" looks like a deliberately joint board. The plan has
no way to express that — boards are not shareable (`SHAREABLE_TYPES` in
`services/streams.py`).
- If it is not meant to be joint: a migration that nulls every
  `default_board_thread` whose thread belongs to another user, and
  `board_thread_for` ignoring a thread that is not the user's.
- If it is: that is a new feature (shared boards, with write access), and the
  current behaviour is an unintended version of it.

### 2. A shared complex observation shows the unshared observations attached to it

- [x] Decided: intended — reproduced

Decided: sharing a complex observation shares everything attached to it. Attaching
needs ownership, so this only ever shares the sharer's own observations. The viewer
reads them on the complex observation's page: the read-only shared page and the
closed observation page now carry the Attached list and "Events from attached", and
`ComplexPresenter` no longer filters by user. The attached observation's own page
stays closed to the viewer, so the attach and detach events name it and link to it
only for someone who can open it (`stream_visible_to`). The detach event shows the
title instead of the stream id. Design point 7 in `multiuser-event-streams.md` says
so now.

What follows is the problem as found.

`tasks/templates/tree/events/observation_attached.html` prints
`event.observation.situation_truncated` (the first six words of the *attached*
observation) and a link to it. Both pages a viewer gets render every event of the
stream through the event partials:
- the read-only shared page (`_shared_observation`, `views_observation.py:472`);
- the closed observation page (`observation_closed_detail`, `views_observation.py:331`).

So when Alice shares complex observation C with private A attached, Bob reads A's
first six words and its id on C's page. The link itself answers 404 for him. Once A
is closed the page shows A's stream id instead (`observation_detached.html` always
shows the raw stream id).

`ComplexPresenter(stream, user)` and `/observations/<id>/attachments/` filter this
correctly; only the event partial goes around it. This contradicts design point 7
("sharing a stream shares its member events, nothing else").

Fix direction: the attach/detach partials show the other observation only when the
viewing user can access its stream, otherwise a neutral "an observation".

### 3. Two browsable-API forms list every user's observations and trips

- [x] Fixed — reproduced by the audit; querysets confirmed by reading

Fixed: `updates/` filters through `ObservationUpdatedFilter`, whose
`observation_id` chooses among the observations the caller can see
(`visible_to`, as the list itself reads), and the journal's `story` is an
`OwnStoryField` over the caller's own trips. The browsable API lists only those, and
someone else's id now answers like an unknown one (400 with the same message).

What follows is the problem as found.

DRF's HTML renderer is on (`REST_FRAMEWORK` in `tasks/settings/base.py` sets no
renderers), so opening an API URL in a browser renders filter and POST forms.

- `ObservationUpdatedViewSet.filterset_fields = ["observation_id"]`
  (`views_observation.py:163`) becomes a `ModelChoiceFilter` over
  `Observation.objects.all()`. `/updates/` in a browser shows a `<select>` of every
  user's open observations, labelled with date, first six words and thread. In JSON,
  `?observation_id=<someone else's>` answers 200 empty and an unknown id 400, which
  tells the two apart.
- `story = PrimaryKeyRelatedField(queryset=Story.objects.all())`
  (`serializers.py:216`). `/journal/` in a browser shows a `<select>` of every user's
  trip titles. `validate_story` answers "Story not found for this user." for a
  foreign id and "Invalid pk" for an unknown one.

Fix direction: the pattern already exists in `OwnObservationField` and
`UserThreadField` (a field whose queryset reads the request). Declare the filter
explicitly with a request-scoped queryset, as was done for `event_stream_id`.

### 4. The attach picker offers shared observations that cannot be attached

- [x] Fixed — read; reproduced by the audit

Fixed: in attach mode the observation lists show only the user's own observations,
and `observation_search` with `observation` searches only those. Outside attach mode
both still show shared ones. The list's "Enter Attach Mode" button is offered only on
the user's own observations.

What follows is the problem as found.

`ObservationListView` (`views_observation.py:253`) and `observation_search`
(`views_observation.py:854`, `:901`) use `visible_to`, while attaching requires
ownership (`_validate_event_stream_id`). In attach mode a shared observation gets a
checkbox, and ticking it answers "Observation does not exist". No leak.

Fix direction: when the search or list is used for attaching (the `observation`
parameter is present), use `owned_by`.

## "As built" notes that don't match the code

### 5. Stage 6 — the route isolation test is weaker than described

- [ ] Strengthen the test — reproduced

The note says the test calls every route "as a second user pointed at the first
user's objects". For most detail routes it does not, because `url_kwargs`
(`tests/test_route_isolation.py`) has one value per parameter *name*:
- `pk` is always a journal entry id, so the detail routes of boards, plans,
  reflections, observations, updates, observation events, habits, threads, profile
  and stories get an unrelated id;
- `id` is a `BoardCommitted` id, so `boards/<id>/commit/` (which takes a board id)
  never targets Alice's board;
- `event_stream_id` is always the closed observation's, so
  `projected-outcome/<uuid>/events/` is never pointed at her outcome.

Other limits:
- JSON bodies only: form views read `request.POST`, see nothing and stop before any
  lookup; the browsable API is never rendered (item 3 went unseen);
- no query strings: `?thread=`, `?observation_id=`, `?event_stream_id=`, `?q=`,
  `?date=`, `?features=` are untested;
- one fixed payload: most writes answer 400 on a missing field before reaching the
  scoping code, which passes;
- Bob never has viewer access, so `owned_by` / `visible_to` mix-ups and viewer
  writes are invisible (item 2 went unseen);
- the detector is the literal `SECRET` and five stream ids: counts, names and
  400-versus-404 differences go unnoticed;
- the fixture is pinned to 2026-11-10 while the today page, daily events and
  current-month archives use the wall clock.

A rerun with the right id for each route, form-encoded bodies and query strings
(1,919 calls) found no leak and no change to Alice's data, so the code is sound
here. The test would not catch a regression.

To do:
- [ ] ids per route name, not per parameter name;
- [ ] form-encoded bodies next to JSON, and a set of query strings on GET;
- [ ] a second walk where Bob is a viewer of a shared trip, open observation, closed
  observation and outcome: nothing private shows, nothing of Alice's changes;
- [ ] render the browsable API (`Accept: text/html`) for the API routes;
- [ ] check the rendered pages for a `<form>` inside another `<form>`. A test that
  posts to the views can't see a broken page (item 9 went unseen).

### 6. Stage 4 — `ensure_stream_entries` is not run by the deploy

- [x] Run once on production — read

Done: `ensure_stream_entries` was run on production by hand.

The plan says the idempotent SQL runs after deploy. `.github/workflows/deploy.yml`
runs `migrate` and swaps the containers; nothing runs
`manage.py ensure_stream_entries`. An event the previous release saved between 0088
and the container swap has no home entry. Such an event is missing from everything
that reads through `Event.visible_to` — the observation timeline, the
observation-events API — even for its owner; `owned_by` pages still show it.

The dev copy has no event without a home entry, but it was migrated in one go, so
that says nothing about production. The command changes nothing when nothing is
missing. Only that one deploy needed it; later releases keep entries through
`Event.save`.

### 7. Stage 5 — admin writes are not always credited to the stream's owner

- [x] Code corrected — read

Fixed: the action no longer passes `created_by`, so the close is credited to the
observation's owner, as the note says.

The note says anything outside request paths, "the admin" included, defaults to
whoever started the stream. The "Close selected observations" action passes
`created_by=request.user` (`admin.py:51`), so an admin closing another user's
observation is recorded as its writer. Either is defensible; the note and the code
should agree.

### 8. Stage 5 — "production has one such observation"

- [x] Checked — data

Closed without change: nothing to fix in the data or the code.

The note says production has an observation filed under another user's thread, which
makes deleting that user fail. The dev copy has none: every observation's user is
its thread's user, and every event's thread owner is its stream's creator. Either
the data was fixed since or the note describes the older dump.

## Broken by this work

### 9. The observation editor can't save, share or stop sharing

- [x] Fixed — clients (Chrome)

Fixed: the whole drawer moved after `</form>`. A wrapper `div.observation-editor`
is the grid now and carries `data-observation-id`. The `<form>` inside it has
`display: contents`, so its topbar, form column and updates stay on that grid.
`tests/html.py` has `nested_forms()`, and the editor page is checked with it. In
Chrome, on tester's observation 438: Share and Stop sharing post to
`/streams/<id>/sharing/` and update the panel, and Save posts the editor with the
Username box empty. The layout and the drawer look as before.

What follows is the problem as found.

`observation_edit.html:120` includes `tree/_stream_sharing.html` inside
`<form class="observation-editor">` (lines 15–186). An HTML parser drops a `<form>`
start tag inside another form, so the panel's Share and Stop sharing forms disappear
from the page. Their inputs, including the required `username` text box, become
fields of the editor form. For the owner of any open observation:
- **Save does nothing** while the Username box is empty, because the editor form is
  invalid. With the drawer closed nothing visible happens and no request is sent;
  with the History drawer open, Chrome shows "Please fill in this field" on the
  Username box.
- **Share** with a username typed in submits the editor (`POST /observations/<id>/`)
  instead of `POST /streams/<id>/sharing/`. The observation and its updates are
  saved; access is not changed.
- **Stop sharing** does the same: the editor is posted and the viewer keeps access.

The trip, closed observation and projected outcome pages include the panel outside
any form, and sharing and revoking work there. Introduced by `950fb51`. The tests post
to the views directly, so they pass.

Fix direction: render the panel outside the editor form. Nothing in the drawer is an
editor field (the attach search has no `name`, and the detach buttons are
`type="button"`), so the whole drawer could move after `</form>` if the
`.observation-editor.with-drawer` layout allows it.

## New users

### 10. `stats` in the CLI fails until the word count has been computed

- [x] Fixed — clients (CLI)

Fixed in the CLI: `word_count` and `word_count_updated` are optional, and `stats`
prints "not calculated yet" without them, as the web page says "Not calculated". The
server keeps answering null, which says that more truly than 0. Checked by feeding
tester's `/stats/json/` from the dev server to `show_stats`: the old model fails with
the pydantic error, the new one prints, and a computed count prints as before.

What follows is the problem as found.

`get_word_count_statistic` (`utils/statistics.py:168`) returns `(None, None)` when the
user has no `Statistics` row. `/stats/json/` passes the nulls on, and the CLI model
(`cli/src/tasks_collector_tools/models.py:285`, `word_count: int`) rejects them, so
`stats` in the `tasks` shell fails with a pydantic error. The fallback predates this
work. Now that `Statistics` is per user, every new user hits it until
`update_word_count` next runs. The web `/stats/` page renders fine.

Fix direction: make the two CLI fields optional, or answer 0 and no date for a user
without a row.

## Planned and not done, without a note

- [ ] **`Board.thread` NOT NULL** (Stage 1a). Still `null=True` (`models.py`, class
  `Board`). The dev copy has no board without a thread, so it is one migration. A
  board without a thread is invisible to everyone, since boards are found through
  `thread__user`.
- [ ] **`seed_dev` command for the Sidetrack thread** (Stage 1a). The fixture was
  reduced to observation types, the command was not written. The board UI no longer
  needs it: its "Move to" menu now lists the user's own threads (and the boards
  shared with them) instead of a fixed Sidetrack / Daily / Read / Trash list, so a
  user without Sidetrack isn't offered it (Stage 8). A dev database without the
  thread only lacks that board.
- [ ] **Owner queryset methods for `Plan`, `Reflection`, `Board`, `Habit`,
  `Breakthrough`** (Stage 6). Views filter on `thread__user` / `user` inline
  instead. Works; the note could say so.
- [ ] **Migration tests** for "a journalized dangling attachment" and "a NULL-thread
  board" (Verification). Not written. Low value now that the migrations have run on
  production.
- [ ] **Doc upkeep**: the target model still says `PROTECT` for `Event.event_stream`
  and `Event.created_by` (built as `RESTRICT`); "Critical files" lists the deleted
  `uuid_generators.py`.

## Smaller risks

- [ ] **Ownership is answered four ways**: `thread.user`; `Observation.user`,
  `Story.user`, `breakthrough.user`; the owner row in `EventStreamAccess`; and
  `EventStream.created_by`. They agree on every row of the dev copy and nothing
  enforces it. Several checks read `created_by`, which the plan says is provenance
  only and never decides access: `views_observation.py:353` (`is_owner`),
  `views_breakthrough.py:112,150`, `insights_list.html` (`insight.created_by_id`).
  `utils/statistics.py` uses `thread__user` where the pages use `owned_by`. All of
  these give the right answer today and the wrong one once an editor can write to
  someone else's stream. The editor role now exists for boards only (Stage 8). Board
  code decides by access (`editable_by`), and none of the `created_by` checks above
  are on board paths. Settle it before editors reach other stream types.
- [ ] **One trip per event is no longer enforced by the database.** `Story.add`
  (`models.py`) checks, then inserts; two concurrent adds of one event to two trips
  can both pass. `StoryEvent`'s one-to-one used to refuse the second.
- [ ] **`JournalTag` is global**: every user sees and can use all tag names
  (`views.py`, `forms.py`, `serializers.py`). A user created in the admin sees every
  tag name of the production copy in the tag list on `/diary/add/` (clients). The
  CLI's `-T <tag>` fails unless the tag already exists. Not in the plan; decide
  whether tags are per user.
- [ ] **Sharing by username tells whether a username exists** ("There is no user
  called …"). Inherent to the design; acceptable among known users.

## N+1 queries (not from this work)

- [ ] Fix — data, clients

Counted as the owner of the production copy on the dev database. No eager loading was
removed by this work (`git diff e81a606 HEAD` shows `select_related` /
`prefetch_related` only added), so these come from before it. The counts grow with
the user's habits, keywords or rows per page.

| Route | Queries | Repeated per row |
|---|---|---|
| `/habits/<slug>/` | 94 | the habit, per `HabitTracked` (87) |
| `POST /api/v1/android/trip/note/` | 90 | keywords, per habit (28) |
| `/habit/keywords/mine/?all=true` | 76 | the habit, per keyword (36) |
| `POST /journal/` | 58 | keywords, per habit (28) |
| `/events/`, `/events/<year>/<month>/` | 56 | the habit, per `HabitTracked` (34) |
| `/profile/` | 48 | the habit, per keyword (21) |
| `/habit/keywords/mine/` | 47 | the habit, per keyword (21) |
| `POST /habit/track/` | 40 | keywords, per habit (28) |
| `/habits/`, `/habit-api/` | 32 | keywords, per habit (28) |
| `/api/events/daily/` | about 4 per event | thread, tags, habit and its keywords, per event |
| `/journal/`, `/boards/`, `/observation-events/` | 14–35 | the thread, per row (10 a page) |

Most of it has two sources:
- `Habit.get_keywords()` (`models.py:439`) runs `values_list` on every call, so a
  prefetch can't help. Its callers are `build_keyword_to_habit_map`
  (`services/journalling/habit_extraction.py:134`, run on every journal entry, trip
  note and habit line) and `HabitSerializer.get_keywords` (`serializers.py:50`).
  `HabitKeyword` carries `user` now, so one
  `HabitKeyword.objects.filter(user=…).select_related("habit")` can build the map.
- `HabitKeywordSerializer` nests `HabitSerializer` (`serializers.py:73`) over
  querysets without `select_related("habit")`. The habit-event templates read
  `event.habit` the same way.

The rest is a missing `select_related("thread")` on the API viewsets (for example
`JournalAddedViewSet.get_queryset`, `views.py:68`).

Pages for shared items keep a fixed query count: a viewer's trip page with 106
entries runs 9 queries, and an observation with 51 updates 14.

## Older bugs met on the way (not from this work)

500s:
- [ ] `/diary/<unknown-slug>/` — `JournalTag.DoesNotExist` instead of 404
  (reproduced, clients). `/diary/2026/` lands on the same route.
- [ ] Photo upload confirm (`POST /api/v1/android/photo/`,
  `/api/v1/android/trip/photo/`) when the bucket can't be reached —
  `object_exists` (`services/photos/storage.py:115`) lets botocore's
  `EndpointConnectionError` through. A storage outage should answer 503 (clients,
  on dev with MinIO unreachable).
- [ ] `POST /plans/` and `POST /reflections/` with a valid body — the serializers
  have no `thread`, so the insert fails (reported by the audit; the serializers were
  not changed by this work).
- [ ] `/habit-api/?date=x` and `/api/events/daily/?date=x` with a malformed date
  (reported by the audit, not rerun).
- [ ] `POST /updates/?observation_id=<own>` — picks a serializer without the
  observation (reported by the audit, not rerun).

Not 500s:
- [ ] `boardmd` fails with `KeyError: 'state'` (`cli/.../boardmd.py:72`) on a board
  that holds a task added through `/boards/append/` or the Android app:
  `create_task_item` (`board_operations.py:11`) keeps the state under `data` and
  writes no top-level `state` (clients).
- [ ] The CLI `journal` saves entries an hour off in CET: the template's naive
  `> Published:` time is read as UTC (`TIME_ZONE = "UTC"`) (clients).
- [ ] Tracking a keyword the user doesn't have (CLI habit line, `/habit/track/`)
  records nothing and still answers `{"ok": true}`; the CLI prints "Habit tracked"
  (clients).

## Cosmetic

- [ ] The breakthrough page's "Shared with you" list sits below the two-column layout,
  flush against the sidebar (clients).
- [ ] The closed observation page shows a raw `timedelta` ("Opened for 838 days,
  0:41:48.069851") and prints `None` for empty interpretation and approach (clients;
  from `a505b09`).

## Dev environment

- [ ] **MinIO can't be reached.** `development-tasks-minio-1` is on no Docker network
  the backend shares, so `tasks-minio` doesn't resolve, and port 9000 isn't published
  to the host. Presigned photo URLs (`localhost:9000`) don't load in the browser, and
  photo upload confirms answer 500. Photo flows can't be tested on dev until this is
  fixed.
- [ ] **`android/local.properties` has a token the dev database doesn't know**
  (401 "Invalid token."), since the database was rebuilt from the production dump.
  `android/scripts/get-android-token <user> --server http://10.0.2.2:8000 -f`
  replaces it.
- Test data from the second pass stays on dev, marked `[chrome-test]`,
  `[android-test]` or `[cli-test]`:
  - user `tester` (pk 4) with observations 438 and 439, trips 17 and 18 (18 still
    active), the 2026 breakthrough with outcome 29, journal entries and habit
    records;
  - on dragonee: trip 19 with two notes, a `#workout` habit record, and a CLI note in
    trip 16;
  - tester's "Shared-test" thread (pk 24), whose board holds three `[chrome-test]`
    tasks (one moved there from django's Daily by a commit, 9815);
  - dev auth tokens for both users.

  Every share made during the testing was revoked. The one share left is karolina's
  editor access to "Razem", which 0093 created.

## Checked and found sound

For the record, so it is not rechecked needlessly:
- a stranger gets nothing from any route, with correct ids, form bodies and query
  strings, and changes nothing;
- a viewer's writes are all refused: observation updates, edit, close,
  close-and-extract, journalize, attach and detach both ways, stream sharing (a
  viewer cannot pass it on), trip note / stop / share / photo presign, outcome
  close / evolve / move;
- hidden ids in the breakthrough and observation-update formsets, a foreign thread
  in the observation form and a foreign journal in habit tracking are rejected;
- `created_by` is the acting user on every request path;
- shared trip notes stay out of the viewer's diary, event archive, today page and
  daily events;
- photo presigning, sidebar counts, statistics, habit keywords, the Celery task and
  the management commands are per user;
- on the dev copy: every stream has exactly one owner row, equal to its creator;
  every event has its home entry; no `HabitTracked` sits outside its habit's stream.

From the clients (second pass):
- a user created in the admin gets Daily, Weekly and big-picture with their boards
  and streams, a profile, and the `poi` and `weight` habits;
- the CLI and the Android app show a stranger none of another user's data. The CLI
  refuses `observationdump --stream <someone else's stream>`, `update <id>` and
  `journal --story <id>` for objects it doesn't own. Android's trip and
  photo-original endpoints answer 404 for another user's trip and photo, and a habit
  line or keyword naming another user's habit writes nothing to it;
- sharing and revoking from the trip and projected outcome pages work over HTMX.
  Shared items appear under "Shared with you" on the trips list, the observation
  lists ("shared by"), insights ("View timeline") and the breakthrough page, and
  open read-only. Sharing with yourself or an unknown user answers with a message;
- a viewer's personal pages and APIs (today, diary, event archive, journal,
  summaries, stats, daily events) show nothing of a shared trip or observation.
  `/observation-events/` does list a shared observation's events, which is
  intended (`visible_to`), and returns no attach or detach events at all;
- Android: tasks (add, complete with a note, save to trip, move, delete) and trips
  (start, note with `#poi`, retry with the same idempotency key, rename, public
  share and revoke, stop, a note on a stopped trip → 409). Trip notes and their POI
  `HabitTracked` rows join the trip stream. The public share link doesn't touch the
  stream's access list;
- every event written through the clients has the acting user as `created_by`, the
  right home stream and its home entry;
- intended, so not to be rechecked: the today page shows yesterday before noon
  (`get_period_from_request`); the board heading reads "Invalid date" until
  `/boards/` has loaded.
