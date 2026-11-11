# Tasks

How Tasks Collector knows what a task is. Current as of 2026-11-11 (migrations
through 0101). "What is next" lists what is planned and not built.

## Language

- A board is a tree of items. An item is an **unscheduled task**: something to do
  that isn't planned yet. It has no row of its own; it is a node of `Board.state`.
- A **task** is something planned: for a day, a week, a month. It has a row
  (`Task`), and it stays once it is done.
- A task is made when a board item is planned, when a line is written into a plan,
  or when something is added from the phone. A task written into a plan is not
  written to a board.

## Model

```python
class Task(models.Model):
    id = UUIDField(primary_key=True)
    user = FK(User)                 # who made it; provenance
    text = TextField()              # may carry a step counter: "Do x (3)"
    done_count = PositiveIntegerField(default=0)
    completed_at = DateTimeField(null=True)   # set when done_count reaches total
    anchor = CharField(max_length=8, unique=True)
    board = FK(Board, SET_NULL, null=True)    # the item it was planned from
    board_item_id = CharField(null=True)
    event_stream = FK(EventStream)  # the stream of a board

class PlanLine(models.Model):       # a plan is its lines, in order
    plan = FK(Plan, related_name="lines")
    position = PositiveIntegerField()
    task = FK(Task, null=True)      # a line with a task shows the task's text
    text = TextField()              # a plain line: no task
    # unique (plan, task)

class ReflectionLine(models.Model): # good, better, best: three lists of lines
    reflection = FK(Reflection, related_name="lines")
    field = CharField(choices=Field)
    position = PositiveIntegerField()
    text = TextField()              # the line's own wording
    task = FK(Task, SET_NULL, null=True)
    completion = FK(TaskCompleted, SET_NULL, null=True)

class TaskCompleted(Event):         # one per step done; deleted when taken back
    task = FK(Task)
    day = DateField()               # the day it was done on, for who did it
    text = TextField()              # "Do x (2)"
    journal = FK(JournalAdded, SET_NULL, null=True)
```

`Plan` and `Reflection` are unique per `(thread, pub_date)`.

- **Done is the task's.** `task.done` is `done_count >= total`, and `total` is the
  counter in the text (one without a counter). Every plan the task is on shows it
  done: a task of the week ticked on Tuesday is done in the week and on Wednesday.
- **One task, several plans.** A task on the day's, the week's and the month's plan
  has three `PlanLine` rows.
- **A counted task** keeps its steps when it moves to another day. Each step is a
  `TaskCompleted`; a step past the total is allowed ("add another").
- **A board item names its task** in `data.taskId`; the task names the item in
  `board` and `board_item_id`. Planning an item whose task is done makes a new task
  for it.

## Access

A task lives in the stream of a board (`Thread.board_stream`): the board its item
is on, or its maker's default board (`board_operations.board_thread_for`) when it
was typed into a plan. Whoever has access to the board has access to the task:
`Task.objects.visible_to(user)`, `editable_by(user)`.

- An item of a shared board is one task for everyone. Whoever plans it second gets
  the same task on their own plan.
- Anyone who can change the board can complete it. The reflection line goes to who
  completed it and to everyone who has the task on a plan, each in their own Daily
  reflection.
- A `TaskCompleted` is filed under the board's thread, in the board's stream, like
  `BoardCommitted`. It shows in the event archive of the board's owner.
- If someone's default board is one shared with them, the tasks they type into
  their own plans live in that shared stream.

## Lines and text

The rows are what is true. `Plan.focus` and `Reflection.good|better|best` hold the
same lines joined with newlines, for everything that reads text: the day page's
forms, `plans/`, `reflections/`, `api/events/daily/`, the CLI, the Android app's
week section.

Text can be written into a column without the rows knowing (a form, the API, the
admin, a release that predates the rows). `services/tasks/documents.py` handles
both directions:

- `plan_for` / `reflection_for` are how code gets a document. They call
  `ensure_lines`, which makes the rows say what the text says.
- `sync_lines(doc, create_tasks)` does the same for text someone wrote as a plan
  (the day page, `plans/`): with `create_tasks`, new lines become tasks.
- Every change to rows ends with `write_cache`, which sets the columns. A column
  that already says what the rows say is left alone, line endings included.

How rewritten text maps onto rows:

| The text now | Plan | Reflection |
|---|---|---|
| line unchanged | row and task kept | row and link kept |
| line reworded in place | the task is renamed | the line keeps its task |
| line taken out | task off this plan | line gone; the task stays done |
| same text typed elsewhere in the same save | still that task | still that link |
| new line | a task¹, or a plain line | a plain line |

¹ On the Daily, Weekly and big-picture plans, from yesterday's plan on, for a line
with a letter or a digit in it. Elsewhere a typed line is a plain line; it becomes
a task when something is done with it (ticked, moved, pulled into a day).

"Reworded" is a guess from how alike two lines are (`REWORDED_RATIO`). It goes
away for the web once the editor knows which line is which (see "What is next").

A task taken off its last plan is deleted unless something remembers it: it was
done at least once, or it is linked to a board item.

## Operations

`services/tasks/operations.py`. Each is one transaction; rows are locked board,
then task, then plans and reflections.

- `plan(task, plan)`, `unplan`, `move`, `rename`.
- `task_for_item(user, board, item)` — the task of a board item, made if needed.
- `complete(task, actor, day=, at=, mark=, note=, story=, idempotency_key=)`:
  1. a `TaskCompleted`, once per idempotency key;
  2. a reflection line for the actor and the other planners — good, or better /
     best for the mark `~` / `^`;
  3. the board item ticked once the task is done;
  4. with a note or a trip, a `JournalAdded` (`- [x] text` and the note). It is not
     run through `process_journal_entry`, which would complete the task again.
- `reopen(task)` takes back the last step: its event and reflection lines go, the
  item is unticked. Removing a reflection line never reopens a task.

`services/tasks/agenda.py` reads a plan as tasks to show (`plan_tasks`), used by
`api/v1/plans/today/` and the Android list. A plain line is done the way it was
before tasks had rows: when its text is in the same period's reflection.

## API by task id

`views_tasks.py`, for clients that know which task they mean. A token, basic auth
or the session, as everywhere. A task the caller can't change answers 404, like
one that doesn't exist. Every date comes from the client: the server's day is a
different one for part of every night.

| Method and path | Body | Does |
|---|---|---|
| `GET api/v1/tasks/agenda/?date=` | | the plans of that day, its week and its month |
| `POST api/v1/tasks/` | `date`, `thread`?, and `text` or `board_id` + `item_id` | plans what was typed, or a board item; returns the task |
| `GET api/v1/tasks/<id>/` | | the task |
| `PATCH api/v1/tasks/<id>/` | `text` | renames it, on every plan and on its board item |
| `POST api/v1/tasks/<id>/plan/` | `date`, `thread`? | puts it on another plan too |
| `POST api/v1/tasks/<id>/unplan/` | `date`, `thread`? | takes it off a plan; 204 when the task is gone |
| `POST api/v1/tasks/<id>/move/` | `from_date`, `to_date`, `thread`? | to tomorrow, to next week |
| `POST api/v1/tasks/<id>/complete/` | `day`, `at`?, `mark`?, `note`?, `story_id`?, `idempotency_key`? | does a step |
| `POST api/v1/tasks/<id>/reopen/` | | takes the last step back |

`thread` is `Daily` (the default), `Weekly` or `big-picture`, and a `date` names
the plan of that thread it falls in. A task comes back as:

```json
{"id": "…", "anchor": "91bd0a44", "text": "Do x (3)", "display": "Do x (2/3)",
 "done": false, "mark": null, "total": 3, "done_count": 1, "completed_at": null,
 "board": {"id": 12, "item_id": "…", "thread": "Inbox"},
 "plans": [{"thread": "Daily", "pub_date": "2026-11-11"}]}
```

`plans` are the caller's own. In an agenda, a plain line has `id` null; posting
its text to `api/v1/tasks/` with the same `date` and `thread` makes it a task.

Also by id: `plans/add-task/` takes `board_id` and `item_id` (its `text` is for
clients that don't send them), and `api/v1/android/board/items/` gives each item's
`id`, `board_id` and whether it is `planned`.

## Anchors

A task's `anchor` names it inside text: a line that ends with ` ^t91bd0a44` is
that task's line, whatever its wording (`documents.split_anchor`, `anchored`).

A journal line `- [x] Called them, at last ^t91bd0a44` completes that task and
puts the line, as worded, into the reflection as the task's. The anchor works for
any task its author can change, planned for that day or not. If the task is
already that far along (a week's reflection repeating a day's), the line is added
as the task's and nothing is done twice. Anchors are taken out of the entry's
stored text. An anchor that names no task of the author's is dropped and the line
is read by its text.

## Boards

- `Board.save` keeps items in one shape (`services/boards/items.py`).
- The web board saves the whole tree and may hold one from before an item was
  planned. `BoardViewSet.perform_update` calls `board_links.reapply`: which task an
  item has is the task's to say, not the tree's.
- A commit carries `taskId` with items that stay or move. `board_links.follow`
  then updates the tasks: one whose item moved follows it (and its stream), one
  whose item left the boards is unlinked, and a done task's item that stays (a
  repeating item) is unscheduled again.
- Ticking a linked item on the web board does not complete its task yet.

## Text from clients that don't know ids

`services/today/operations.py` serves `api/v1/android/task/*` and `plans/add-task/`.
A client names a task by the text of its line; the lookup is, in order: a line of
that plan; the task of that text on the week's or the month's plan, or an open one
on a recent day; the board item of that text; a new task. A counted task is found
with its counter in any form (`Do x (3)`, `Do x (2/3)`).

A journal line marked `[x]` / `[~]` / `[^]` (`services/journalling/`) completes the
task of that text planned for that day, week or month. Failing that it ticks the
unscheduled task of that text on the author's board. Otherwise it is a reflection
line of its own.

Text is only used there, to find what a typed line means. Nothing is linked by it.

## History

Migration 0101 gave every line of every plan and reflection a row, and made tasks
of the lines of the plans whose period was not over (Daily from the day before,
the current Weekly and big-picture). Older lines are plain lines, word for word.

## What is next

1. Web board: plan by item id, a planned badge, ticking and renaming a linked item
   completes and renames its task.
2. Day page: one editor over text with anchors drawn as chips; saves applied as a
   diff against what the page loaded.
3. Android and CLI by task id.
4. The text endpoints and the text columns go.
