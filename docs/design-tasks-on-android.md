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
device's. None of them is made from the screen: each is queued in the outbox and
sent by its worker (see "Offline").

| What the user does | Call |
|---|---|
| types a task | `POST api/v1/tasks/` `{text, date}` |
| "Add to today" on a task of the week, "Copy to today" | `POST <id>/plan/` `{date}` |
| picks items in the board picker | `POST api/v1/tasks/` `{board_id, item_id, date}` each |
| ticks a task, "Add another" | `POST <id>/complete/` `{day, at, note, story_id, idempotency_key}` |
| unticks, "Reset" | `POST <id>/reopen/` `{done_count}` |
| "Move to tomorrow" | `POST <id>/move/` `{from_date, to_date}` |
| "Remove" | `POST <id>/unplan/` `{date}` |

- A task typed in is not written to the board. "Remove" takes it off the day's
  plan and leaves the board alone.
- `day` is the day being viewed; `at` is the moment of the tap with the date
  swapped to that day, so a note's journal entry is filed under it too.
- `idempotency_key` is the id of the queued call, one per tap: a request sent
  twice completes once.
- `done_count` is how many steps the row showed done when it was unticked. The
  server takes a step back only while the task has that many, so the request
  sent twice takes back one.
- `note` makes a journal entry (`- [x] text` and the note); `story_id` ("Save to
  trip") links it to the active trip. A stopped trip answers 409 and nothing is
  written; the call stays on the screen as one that couldn't be sent.

The board picker lists `GET api/v1/android/board/items/` (the user's current
board, flattened, each item with its `id`, `board_id` and whether it is
`planned`) and appends an unscheduled task with `POST boards/append/`. Those two
are made directly: the picker has nothing to show without a connection.

## Offline

What is done to a task is written to the outbox (`data/Outbox.kt`, the queue
that carries trip notes and photos) as a `TaskOp`, and the outbox worker makes
the call: at once when there is a connection, otherwise when there is one again,
after the app was killed or the phone restarted too.

- **The lists show it done already.** They are what the server last said with the
  queued calls on top (`withPending` in `data/TaskOp.kt`): a tick shows at once
  and stays through an offline spell. A call that was sent is kept on top until
  plans fetched after it are in (`QueuedTaskOps`), so nothing flickers back.
- **A task without an id** (a plain line, a task typed in and not sent yet) is
  named by its text on the plan of the day. The drainer plans that text there to
  get the id, and writes the id into the queued call before using it. So a task
  can be typed in and ticked with no connection: two calls, sent in order.
- **Order.** Task calls are sent in the order they were made, before any photo
  (a tick doesn't wait for an upload). One that has to wait (no connection, a
  5xx) holds back those after it: an untick sent ahead of its tick would leave
  the task ticked.
- **Sent again, a call changes nothing more.** Planning a task that is on the plan
  is a no-op, a completion has its key, a step is taken back from the count the
  user saw, a move finds the task where it put it, and taking a task off that is
  gone (404) counts as done.
- **A call the server refuses** (a 4xx: the trip is stopped, the task is gone) is
  not retried. It is listed above the tasks with Retry and Discard, and the list
  does not show it done. A line says how many calls are waiting once they have
  waited two seconds.

The plans are kept too (`data/SavedPlans.kt`): every agenda fetched is saved
for its day, and opened with no connection the lists are the day's plans as
last fetched, with the queued calls on top, and a line says when they were
fetched. A day never fetched shows only what is queued for it.

- **Today and tomorrow are fetched in the background** about hourly while there
  is a connection (`sync/PlansRefreshWorker.kt`), so a plan written on the web
  in the evening is on the phone the next morning.
- **Each saved day names the account that fetched it** (a hash of the server
  and the token): logged out, or logged in as someone else, none is shown.
- Days more than two weeks from today are thrown away.

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
├── data/TaskOp.kt            # a queued task call; lists with the queue on top
├── data/Outbox.kt            # the queue (enqueueTask, tasks)
├── data/SavedPlans.kt        # the plans of each day fetched, for offline
├── sync/PlansRefreshWorker.kt # today's and tomorrow's plans, in the background
├── sync/OutboxDrainer.kt     # makes the calls (sendTask), one pass (drain)
├── ui/TodayScreen.kt         # the list, the week section, the dialogs, sync status
├── ui/TodayViewModel.kt      # tasks / weekPlan / pendingComplete / focus
└── ui/BoardPickerViewModel.kt
```

Mutations follow one pattern (`TodayViewModel.queueOp`): queue the call, show the
lists with it, kick the worker. The view model watches the worker and fetches
the agenda again when calls have been sent.

Tests: `app/src/test/.../data/TaskTest.kt` (decoding an agenda, row keys, the
week section, request bodies), `data/TaskOpTest.kt` (the lists with queued calls
on top), `data/OutboxTest.kt`, `data/SavedPlansTest.kt`, `sync/OutboxDrainerTest.kt`
(each call, retries, the order of a pass). The server's side is `tests/test_tasks_api.py`.
