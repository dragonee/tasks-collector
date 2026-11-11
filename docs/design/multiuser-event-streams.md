# Multi-user and stream sharing

How Tasks Collector keeps each user's data private and lets them share parts of it.
Current as of 2026-11-11 (migrations through 0097). "How it was built" lists the
stages; "Open items" lists what is left.

## Login and API access

- Every page needs a login (`/accounts/login/`, `/accounts/logout/`). Without one,
  only the login pages, `/health/` and a public trip link answer.
- The API needs an authenticated user on every route and accepts a token, basic auth
  or the session. The web frontend uses the session, the CLI basic auth, and the
  Android app a token (`manage.py issue_mobile_token`,
  `android/scripts/get-android-token`).

## Model

```python
class EventStream(models.Model):
    id = UUIDField(primary_key=True, default=uuid4)
    type = CharField(choices=Type)  # board, journal, habit, observation, projected_outcome, trip
    created_by = FK(User, CASCADE)  # who started it; provenance
    created = DateTimeField(default=now)

class EventStreamAccess(models.Model):  # the access list; decides permissions
    stream = FK(EventStream, related_name="access")
    user = FK(User, related_name="stream_access")
    role = CharField(choices=Role)  # owner, viewer, editor (boards only)
    # unique (stream, user); one owner per stream

class EventStreamEntry(models.Model):  # which events are in which streams
    stream = FK(EventStream, related_name="entries")
    event = FK(Event, related_name="stream_entries")
    # unique (stream, event)

class Event(PolymorphicModel):
    event_stream = FK(EventStream, RESTRICT, db_column="event_stream_id")  # home
    created_by = FK(User, SET_NULL, null=True)  # who wrote it; provenance
```

- A stream is a row, reached from the object it belongs to and never computed:
  `Thread.board_stream`, `Thread.journal_stream`, `Habit.event_stream`,
  `Observation.event_stream`, `ProjectedOutcome.event_stream`, `Story.event_stream`.
  Each of them creates its stream, with the owner's access row, when it is first
  saved.
- An event has one home stream and may be a member of others. A trip note is a
  `JournalAdded` whose home is the Daily journal stream and which is also an entry of
  the trip's stream.
- `Event.save()` sets the home stream from what the event is about
  (`derived_event_stream_id()`: the thread's journal or board stream, the habit's,
  the observation's, the outcome's) and writes the home entry with it. A journal
  entry or board commit moved to another thread moves to that thread's stream, and
  its home entry follows. Its trip membership stays.
- Stream ids from before this work are kept, so old URLs and CLI `--stream` values
  still work.

## Rules

1. **Everything has an owner.** A user owns their threads, and through them their
   boards, plans and reflections; their habits, habit keywords, statistics,
   breakthroughs, journal tags and profile. Names and slugs are unique per user.
2. **Every user gets the built-ins.** `provision_user` gives a new user the Daily,
   Weekly and big-picture threads with a board each, a profile, and the `poi` and
   `weight` habits. It runs when a user is created and from
   `manage.py provision_users`. The three threads can't be deleted, except with their
   user.
3. **Access is decided by the access list**, never by `created_by`.
   `EventStream.created_by` and `Event.created_by` only record who started a stream
   and who wrote an event. Request paths pass the acting user. Anything else (model
   signals, the admin, Celery) defaults to whoever started the event's stream.
4. **Two scopes.** `owned_by(user)` is for personal pages and for writes;
   `visible_to(user)` is for what can be read, which is the user's own and what was
   shared with them. `Event`, `Observation`, `ProjectedOutcome`, `Story` and
   `EventStream` have both. With one scope, a friend's trip notes would show up in my
   diary once the trip was shared.
   - Personal, so `owned_by`: today, diary, event archive, daily events, statistics.
   - `visible_to`: trip, observation and outcome pages, the observation lists,
     insights, and the `/observation-events/` API.
   - `Plan`, `Reflection`, `Habit` and `Breakthrough` have no such method. Their views
     filter on `thread__user` or `user`.
5. **Sharing a stream shares its member events, nothing else.** A shared trip shows
   its notes, photos and linked POI habit records, not the owner's Daily journal.
   One addition: a shared complex observation also shares the observations attached
   to it. The viewer reads them on the complex observation's page and can't open
   them on their own. Only your own observations can be attached, so nothing of a
   third user's is shared this way.
6. **Trips, observations and projected outcomes are shared view-only.** A viewer's
   writes are all refused, and a viewer can't share further. Sharing sits on the
   stream because `Observation` and `ProjectedOutcome` rows are deleted on close, and
   the stream is what survives to carry the access list.
7. **Boards are shared to edit.** Some boards are joint. Daily, Weekly and
   big-picture can't be shared: every user has one of each, and the names would
   collide on the board page. Board code asks
   `Board.objects.editable_by(user)` and `Thread.objects.board_editable_by(user)`
   (owner or editor, the user's own first).
8. **An id from the request is looked up among what the caller may use.** Fields and
   filters that take an id read the request (`UserThreadField`,
   `OwnObservationField`, `OwnStoryField`, `ObservationUpdatedFilter`). The browsable
   API then lists nothing else in its forms, and someone else's id answers like an
   unknown one.

## Sharing

`services/streams.py` has `share(owner, stream, username)`, `revoke(...)` and
`shared_with(stream)`. Only the owner can share, and never with themselves.
`SHARE_ROLES` says which stream types can be shared and with which role.

- `POST streams/<id>/sharing/` answers HTMX with the re-rendered panel
  (`tree/_stream_sharing.html`). `api/streams/<id>/sharing/` is the JSON version the
  board page uses: GET lists who the stream is shared with, POST takes
  `{"action": "share" | "revoke", "username"}`, and a share that can't be done answers
  200 with `error`.
- Sharing with a username nobody has says so, which tells whether a username exists.
  Accepted among users who know each other.
- The CLI and the Android app have no sharing UI. Both work on a shared board by name
  or as the default board.

Trips, observations, outcomes:
- The owner shares from the trip page, the observation editor, the closed observation
  page and the projected outcome's history.
- A viewer gets the trip page without its controls, a read-only observation page,
  the closed observation without "Extract insight", and the outcome history.
- Shared items are listed under "Shared with you" on the trips list, the observation
  lists ("shared by"), insights and the breakthrough page.
- On a shared complex observation the viewer sees the Attached list and "Events from
  attached". The attach and detach events link to the attached observation only for
  someone who can open it.
- Attach mode and its search offer only your own observations.
- A trip's public link (`SharedStory`) is separate: whoever has the link can read,
  and it doesn't touch the access list.

Boards:
- The owner shares from the board page ("Share" / "Shared with N") or from Account
  Settings ("Shared boards").
- The board API, `/threads/`, `boards/append/` by name, the default board (so the
  Android endpoints and journal ticks) and the profile's default-board choice all
  work on boards the user may edit. `/threads/` and the nested thread in board and
  profile responses carry `shared_by`, `board_stream` and `shareable`; the board page
  shows a shared board as "name (owner)".
- A default board the user can no longer edit is ignored (Daily instead), and
  revoking clears it.
- An editor can commit. Items marked to move go to boards the committing user may
  edit, found by name (their own thread first, then a shared board), never into the
  owner's other boards. The board's "Move to" menu lists those boards.
- The `BoardCommitted` is in the board's stream with the committer as `created_by`.
  `/summaries/` and `board-summary` list commits on your boards and on boards shared
  with you, naming the owner and the committer when they aren't you.

## Deleting a user

- Their streams, the objects those belong to and the events in them go in one
  cascade. The links from an object to its stream and from an event to its home
  stream are `RESTRICT`: a stream can't be deleted while its subject or its events
  exist, except together with them.
- Deleting a user is refused when their events are filed under someone else's thread.
  The production copy of 2026-11-11 has no such event.
- An editor's commits stay on the owner's board as "committed by a deleted user"
  (`Event.created_by` is `SET_NULL`). Deleting the owner takes the board, all its
  commits, the editor's access, and clears the editor's default board.
- Journalizing an observation deletes its events, the observation and the stream.
  Attach and detach events on other observations that pointed at it go with it.

## Photos

Photo originals belong to whoever owns the photo's home stream (the uploader's Daily
journal), for trip and standalone photos alike. Upload keys keep
`trips/{user_id}/{story_id}/…`, and the prefix is only checked on upload. Presigned
URLs are made only for photos the user may see.

## How it was built

Each stage shipped on its own. Owners came before streams, because a stream needs an
owner when it is created, and because the old computed ids gave every user's Daily
the same stream.

| Stage | Migrations | What |
|---|---|---|
| 1 | 0077–0082 | Threads, breakthroughs, habits, habit keywords and statistics get a user; `provision_user` |
| 2 | 0083–0085 | `EventStream` and `EventStreamAccess`; each object creates its stream |
| 3 | 0086 | `Event.event_stream` becomes a foreign key, converted in place |
| 4 | 0087–0089 | `EventStreamEntry`; trips become streams and `StoryEvent` is dropped |
| 5 | 0090–0092 | `Event.created_by` |
| 6 | — | Every view, viewset and service scoped; the route isolation test |
| 7 | — | View-only sharing of trips, observations and outcomes |
| 8 | 0093, 0094 | Boards shared to edit |
| 9 | 0095–0097 | Journal tags per user |

What the data migrations decided:
- Existing data went to one owner: the user named in the migration, otherwise the
  first superuser, otherwise the first user.
- Threads that shared a computed stream id: the first keeps it, the others get a new
  one and their events follow. Board commits and journal entries filed under another
  thread's stream moved to their own thread's.
- The stream backfill stops on an event of an unknown kind or a stream mixing kinds.
- `Event.created_by` was backfilled from the home stream's owner.
- 0093 turned each profile whose default board was another user's custom thread into
  an editor share of that board (on production, the joint "Razem" board), and
  clears a profile pointing at another user's built-in board.
- A journal tag went to that owner if they used it or nobody did, otherwise to
  the first user who did. Every other user who used it got a copy, and their entries
  moved to the copy.
- `manage.py ensure_stream_entries` adds home entries for events the previous
  release saved while Stage 4 was being deployed. The deploy only runs `migrate`, so
  it was run by hand on production, once. It changes nothing when nothing is missing.

## Verification

In the dev containers. The local `.tasks-collector.ini` points at production, so
don't use the CLI to verify.

- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py test`
  (690 tests on 2026-11-11), and `makemigrations --check --dry-run` reports no changes.
- `tests/test_route_isolation.py` calls every route of the app with every method as a
  second user, with JSON and form-encoded bodies and query strings that name the
  first user's objects. It does so as a stranger and as a viewer of a shared trip,
  open observation, closed observation and outcome. No response may contain the
  first user's data (the viewer may see what was shared, nothing else), none may be
  a server error, the first user's data must be unchanged afterwards, and each of
  their ids must answer like an id nobody has. API routes are also rendered as the
  browsable API, and the first user's own pages are checked for a form nested in
  another form. `targets` names the objects each route is called with; a route with
  parameters that isn't listed fails the test.
- Each data migration has a `MigrationExecutor` test (`tests/test_migration_*.py`).
- Reviewed on 2026-11-11 through the web UI, the CLI and the Android app, as the
  owner of a production copy, as a user created in the admin and as a viewer of
  shared items. A stranger got nothing and changed nothing, every viewer write was
  refused, and the viewer's personal pages showed nothing of what was shared.
- On that copy: every stream has exactly one owner, who is its creator; every event
  has its home entry and sits under a thread of its stream's owner.

## Open items

Checked on 2026-11-11 against the code and the dev database.

From this work:
- **`Board.thread` is still nullable.** No board is without a thread, so it is one
  migration. A board without a thread is invisible to everyone, since boards are
  found through their thread's user.
- **Ownership is answered four ways:** `thread.user`; `Observation.user`,
  `Story.user`, `Breakthrough.user`; the owner row in `EventStreamAccess`; and
  `EventStream.created_by`. They agree on every row and nothing enforces it. Some
  checks read `created_by`, against rule 3: `is_owner` on the closed observation
  page, the shared lists on the breakthrough page, the edit link in
  `insights_list.html`. `utils/statistics.py` counts by `thread__user` where the
  pages use `owned_by`. All give the right answer while only owners write to these
  streams. Settle it before editors reach anything but boards. The stream links'
  `RESTRICT` and `EventStream.created_by`'s `CASCADE` need the same look then.
- **One trip per event isn't enforced by the database.** `Story.add` checks, then
  inserts, so two concurrent adds of one event to two trips can both pass.

Older, found on the way:
- **`test_route_isolation` never calls the router's detail routes with an id.**
  `_routes` strips every `^`, which turns `(?P<pk>[^/.]+)` into `(?P<pk>[/.]+)`, so
  `_url` doesn't substitute it and `/boards/(?P<pk>[/.]+)/` is requested literally.
  `boards-detail`, `plan-detail`, `reflection-detail`, `journaladded-detail`,
  `observation-detail`, `observationupdated-detail`, `event-detail`, `habit-detail`,
  `thread-detail`, `profile-detail` and `stories-detail` are in `targets` but only
  ever answer like an unknown URL.
- **500 on a malformed date:** `/habit-api/?date=x` and `/api/events/daily/?date=x`.
- **500 on `POST /updates/?observation_id=<own>`:** the query parameter picks a
  serializer that doesn't set the observation.
- **500 on photo upload confirm when the bucket can't be reached**
  (`/api/v1/android/photo/`, `/api/v1/android/trip/photo/`): `object_exists` only
  catches `ClientError`. It should answer 503.
- **The CLI `journal` saves entries an hour off in CET:** it sends a naive local
  time, which the server reads as UTC.
- **Tracking a keyword the user doesn't have** (`/habit/track/`, a CLI habit line)
  records nothing and answers `{"ok": true}`.
- **Cosmetic:** the breakthrough page's "Shared with you" list sits below the
  two-column layout; the closed observation page prints a raw `timedelta` ("Opened
  for 838 days, 0:41:48.069851") and `None` for an empty interpretation or approach.
- **Dev: MinIO can't be reached.** Its container is on no Docker network and
  publishes no port, so photo URLs don't load and upload confirms answer 500.
