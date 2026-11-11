# Today tasks on Android

How the Today tab of the Android app talks to the backend. What a task is, how
it is stored and who may change it are in `docs/design/tasks.md`; this note is
the app's side.

## What the screen shows

A flat checklist for one day (today by default; the chevrons step through days),
and above it what is left of the week's plan.

- **The day's tasks** come from `GET api/v1/tasks/agenda/?date=<day>` (`daily`).
  Open ones are listed first, in the plan's order.
- **The week section** is `weekly` of the same answer, without the tasks that are
  done and those already on the day (`weekPlanLeft` in `data/TasksApi.kt`). Done
  is the task's, so a task of the week ticked on Tuesday is not offered on
  Wednesday. Long-press offers "Add to today": the same task, on the day's plan
  too.
- A row is told from the others by its task's id (`Task.key`). A plain line of a
  plan (written before tasks had rows, or on the web as plain text) has no id; it
  becomes a task the first time something is done with it (`idOf` in
  `ui/TodayViewModel.kt` plans its text where it is).

## Calls

All under `api/v1/tasks/`, with the token from Settings. Every date is the
device's.

| What the user does | Call |
|---|---|
| types a task | `POST api/v1/tasks/` `{text, date}` |
| "Add to today" on a task of the week, "Copy to today" | `POST <id>/plan/` `{date}` |
| picks items in the board picker | `POST api/v1/tasks/` `{board_id, item_id, date}` each |
| ticks a task, "Add another" | `POST <id>/complete/` `{day, at, note, story_id, idempotency_key}` |
| unticks, "Reset" | `POST <id>/reopen/` |
| "Move to tomorrow" | `POST <id>/move/` `{from_date, to_date}` |
| "Remove" | `POST <id>/unplan/` `{date}` |

- A task typed in is not written to the board. "Remove" takes it off the day's
  plan and leaves the board alone.
- `day` is the day being viewed; `at` is the moment of the tap with the date
  swapped to that day, so a note's journal entry is filed under it too.
- `idempotency_key` is a fresh UUID per tap: a request sent twice completes once.
- `note` makes a journal entry (`- [x] text` and the note); `story_id` ("Save to
  trip") links it to the active trip. A stopped trip answers 409 and nothing is
  written.

The board picker lists `GET api/v1/android/board/items/` (the user's current
board, flattened, each item with its `id`, `board_id` and whether it is
`planned`) and appends an unscheduled task with `POST boards/append/`.

## Counted tasks

A task whose text carries a counter, `Do x (3)`, has steps. The server sends
`total`, `done_count` and the text as lists show it (`display`: `Do x (2/3)`).

- Ticking does one step. The row is checked once all are done.
- Tapping a checked counted task opens a dialog: **Add another** (one more step,
  past the total), **Reset** (takes the last step back) or Cancel.
- A plain task unticks straight away.
- Moved to tomorrow, it is the same task with the steps done so far.

## Dialogs

Ticking a row opens the add-note dialog; the call is made on Save, with the note
if one was typed. "Save to trip" shows while a trip is active.

## Code

```
android/app/src/main/java/org/polybrain/tasks/health/
├── data/TasksApi.kt          # Retrofit interface, Task, AgendaResponse, requests
├── data/TasksClient.kt       # OkHttp + Authorization: Token interceptor
├── ui/TodayScreen.kt         # the list, the week section, the dialogs
├── ui/TodayViewModel.kt      # tasks / weekPlan / pendingComplete / focus
└── ui/BoardPickerViewModel.kt
```

Mutations follow one pattern: show the change, make the call, reload the agenda
whatever the outcome. Task calls are made directly; they are not queued in the
offline outbox (which carries trip notes and photos), so one made without a
connection is lost and the reload shows what the server has.

Tests: `app/src/test/.../data/TaskTest.kt` (decoding an agenda, row keys, the
week section, request bodies). The server's side is `tests/test_tasks_api.py`.
