# Multi-user with stream sharing — staged refactor

## Context

Tasks Collector is single-user in everything but login. Only `Observation`, `Profile`
and `Story` point at a user; `Event`, `Thread`, `Board`, `Plan`, `Reflection`, `Habit`
and `Breakthrough` have no owner, and almost every queryset is global. Stream identity
is ad hoc: a uuid4 column on `Observation` / `ProjectedOutcome` / `Habit`, a
`uuid5(thread name)` for board and journal streams assigned by `pre_save` signals, and
trips sit outside the scheme in a `StoryEvent` join table.

Goal: every stream is a typed `EventStream` row with an access list; an event has one
home stream and may appear in more; sharing grants access to a whole stream (trips,
observations, projected outcomes). Each stage ships on its own and leaves single-user
behaviour unchanged until Stage 6.

Decisions already taken:
- Event keeps **one home stream FK** plus a **membership table** (home included).
- Access rows carry a **role** (`owner` / `viewer`); sharing is **view-only** first.
- **Threads are per-user**; `Daily`, `Weekly`, `big-picture` are provisioned for every
  user and cannot be removed.
- Out of scope: `enfp`, `quests`, `rewards` (being removed).

## Design rationale

1. **Typed EventStream objects — simpler than the earlier draft.**
   The earlier draft (`eventstream-created-by.md`, replaced by this document)
   re-keyed the uuid5 ids to include the user. Not needed: once the owning object holds an FK to its stream there is no generator
   at all. Existing UUIDs become `EventStream` primary keys unchanged, so URLs and CLI
   `--stream` values keep working.
2. **Event in one-or-more streams — this already exists**, as `StoryEvent`: a trip note
   is a `JournalAdded` in the Daily journal stream *and* in a trip. The membership
   table generalises it; the home FK keeps "one `event_stream_id` per event" for the
   serializers and CLI dumps.
3. **`created_by` as provenance only — agreed.** The awkward sites are the
   `ProjectedOutcome*` events created inside model signals with no request in reach;
   those move into the breakthrough service.
4. **Sharing on streams fits the three targets**, partly because `Observation` and
   `ProjectedOutcome` rows are *deleted* on close — the stream is the only thing that
   survives to carry an access list.
5. **The order has to flip: owners first, streams second.** Three reasons, all in the
   code today:
   - A stream needs an owner at birth, but new `ProjectedOutcome`s (formset save) and
     `Habit`s (admin, seed migrations 0068/0074) are created with no user in reach.
     On an empty database (tests, CI) there is no "the one user" to backfill with.
   - `uuid5(slugify(thread.name))` gives every user's `Daily` the *same* board and
     journal stream, so per-user threads and thread-held streams cannot be far apart.
   - Board, journal and habit streams are write-only today; `Plan`, `Reflection`,
     `Board`, `Breakthrough` have no stream at all. Their privacy can only come from
     an owner column. Streams alone do not make the app multi-user.
6. **Two scopes, not one.** "Everything I can access" is wrong for personal surfaces:
   after sharing, it would put a friend's trip notes in my diary. Personal pages use
   `owned_by(user)`; object access and "shared with me" use `visible_to(user)`.
7. **Sharing a stream shares its member events, nothing else** — a shared trip exposes
   its notes, photos and linked POI `HabitTracked` rows, not the owner's Daily journal.

## Target model

```python
class EventStream(models.Model):
    id = UUIDField(primary_key=True, default=uuid4, editable=False)
    type = CharField(choices=Type)  # board, journal, habit, observation, projected_outcome, trip
    created_by = FK(User, CASCADE)   # provenance; see Stage 2 notes
    created = DateTimeField(default=now)

class EventStreamAccess(models.Model):      # the access list; authority for permissions
    stream = FK(EventStream, related_name="access")
    user = FK(User, related_name="stream_access")
    role = CharField(choices=Role)  # owner, viewer  (editor later, no schema change)
    # unique (stream, user); partial unique: one owner per stream

class EventStreamEntry(models.Model):       # replaces StoryEvent
    stream = FK(EventStream, related_name="entries")
    event = FK(Event, related_name="entries")
    # unique (stream, event)

class Event(PolymorphicModel):
    event_stream = FK(EventStream, PROTECT, db_column="event_stream_id")  # home
    created_by = FK(User, PROTECT)
```

Streams are reached from their owner, never computed: `Thread.board_stream`,
`Thread.journal_stream`, `Habit.event_stream`, `Observation.event_stream`,
`ProjectedOutcome.event_stream`, `Story.event_stream`. Each `Event` subclass declares
where its home stream comes from (`home_stream()`), resolved in `Event.save()`.

## Stages

Every "nullable → backfill → NOT NULL" is three migration files (schema, `RunPython`,
constraint); backfills use SQL / historical models, never `.save()`.

### Stage 0 — Prefactor (no behaviour change)
- `tasks/apps/tree/tests/factories.py`: plain helpers `make_thread(user, name)`,
  `make_board(thread, state)`, `make_profile(user, **fields)` wrapping today's
  managers. All `Thread`, `Board` and `Profile` creations in tests go through them,
  so Stage 1 only changes helper bodies.
- `views_observation.py` filtersets: declare `event_stream_id` as an explicit
  `UUIDFilter` (otherwise it silently becomes a `ModelChoiceFilter` in Stage 3).
- Delete dead `on_habit_name_change_update_event_stream_id` (`signals.py:49-61`), the
  only `queryset.update(event_stream_id=…)`.
- `docker/development/scripts/run-development.sh`: `createsuperuser` before `loaddata`.
- This document replaces `docs/design/eventstream-created-by.md`.

### Stage 1 — Owners
**1a. Threads and breakthroughs.**
- `Thread.user` (NOT NULL after backfill to the existing user), `unique(user, name)`.
  Built-ins are the names in a code constant; a `pre_delete` receiver refuses to
  delete them unless the cascade origin is the `User`. `Board.thread` → NOT NULL.
- `Breakthrough.user`, `unique(user, slug)` replaces global `slug` uniqueness.
- `provision_user(user)` (idempotent; called from `post_save(User)` with a `raw`
  guard, from the data migration, and from a management command): the three threads,
  a board each, a `Profile`.
- Every thread lookup is user-scoped via `Thread.objects.for_user(user)`. ~45 sites;
  the user comes from the request (views, forms, `services/today`, `services/photos`,
  `services/trips._journal_thread_for`, `board_operations`) or from `thread.user`
  (`journal_processing.py`, `views_today.py:250`, board transitions).
  `_get_thread_from_breakthrough` (`models.py:680`) uses `breakthrough.user`.
- Scope the list/join sites too, not only `.get(name=…)`: `ThreadViewSet`,
  `/plans/?thread=`, `/boards/?thread=`, `daily_events` (`views.py:362`), the ten
  `SlugRelatedField(queryset=Thread.objects.all())` in `serializers.py` (one field
  subclass reading the request), thread selects in `forms.py`, and
  `ProfileForm.default_board_thread`.
- Dev fixture keeps only `ObservationType`; `Sidetrack` moves to a `seed_dev` command.

**1b. Habits and statistics.**
- `Habit.user`, slug unique per user; `HabitKeyword` unique per user (denormalised
  `user`); drop the "push every keyword into every profile" signals
  (`signals.py:163-177`); `poi` / `weight` habits provisioned per user (migration
  removes ownerless seeds when no user exists).
- `Statistics` keyed per user; `update_word_count` loops over users.
- Scope the global readers: `habit_extraction.py:158`, `views_habit*.py`,
  `services/health`, `views_breakthrough.py:42,79`,
  `services/breakthrough/operations.py:50`, `utils/statistics.py`.

Exit: the existing two-user tests pass with no `MultipleObjectsReturned`; a user
created via admin gets threads, boards and a profile.

### Stage 2 — Streams exist and are born at their owner
- Add `EventStream`, `EventStreamAccess` (admin-registered, `raw_id_fields`).
- Stream FKs on `Thread` (`board_stream`, `journal_stream`), `Observation`, `Habit`,
  `ProjectedOutcome`; each creates its stream (plus the owner access row) on insert.
- Backfill: one `EventStream` per distinct id in `Event`, the three owner models and
  `other_event_stream_id`; type inferred from the event classes (abort listing any id
  with mixed types); owner from the owning row. Existing ids are kept. Threads sharing
  a slug: the first keeps the legacy uuid5, the rest get a new id and their events are
  re-pointed by `thread_id`.
- `Event.save()` calls `home_stream()` when the stream is unset — journal/photo →
  `thread.journal_stream`, `BoardCommitted` → `thread.board_stream`, `HabitTracked` →
  `habit.event_stream`, observation / projected-outcome events → their FK. Also takes
  over the `thread_id` defaulting. Serializers, formsets and admin stay untouched.
- Delete the stream-id `pre_save` signals and `uuid_generators.py`; the helpers that
  migrations 0028/0037 import move to a migrations-only module.

`Event.event_stream_id` is still a plain UUID column here — nothing can violate a
constraint yet. Exit: no code computes a stream id.

As built (0083–0085):
- Owner links (`Thread.board_stream`/`journal_stream`, `Observation`/`Habit`/
  `ProjectedOutcome.event_stream`) are one-to-one with `RESTRICT`: a stream can't be
  deleted while its subject exists, but both go in one cascade when a user is deleted.
  `EventStream.created_by` is `CASCADE` for the same reason. Revisit both with the
  editor role, when streams can hold other users' events.
- `Event.derived_event_stream_id()` is recomputed on every save, as the signals did:
  a journal entry or board commit moved to another thread moves to that thread's
  stream. Stage 4's "refuse a later change of home stream" has to decide this.
- The backfill also moves board commits and journal entries carrying another thread's
  stream id to their own thread's stream (two 2021/2024 board commits in the real
  data), and refuses events of unknown kinds (the dev database has two `discovery`
  events from a removed feature).

### Stage 3 — The constraint
- Assert zero orphan ids, then convert without touching the column: `AlterField` to
  `ForeignKey(EventStream, PROTECT, db_column="event_stream_id", db_index=False,
  editable=False)` followed by `RenameField` to `event_stream`. Hand-written;
  `makemigrations --check` afterwards. Keep the composite index declared on the
  attname so the autodetector sees no diff.
- Same for `ObservationAttached/Detached.other_event_stream`, with `CASCADE`.
- Journalize (`observation_operations.py`) deletes the events, the observation and
  the stream; the cascade removes attach/detach events that pointed at it, which
  until now kept pointing at an observation that no longer existed.

As built (0086): one migration checks that every id has a stream row (it stops
otherwise), then converts the three columns in place: only foreign key constraints
and an index on each `other_event_stream_id` are added. Checked on a pre-stage-0
production dump migrated through 0077–0086.

### Stage 4 — Memberships and trips
- `EventStreamEntry`; `Event.save()` writes the home entry atomically with the insert
  and refuses a later change of home stream. Backfill home entries for every event.
- `Story.event_stream` (type `trip`); `StoryEvent` rows become entries; drop
  `StoryEvent`. One trip per event stays enforced in `services/trips`.
- Convert the `story_entry` readers: `services/trips/operations.py`,
  `services/today/operations.py:88`, `journal_processing.py:46,62`,
  `views_trip.py:52`, `views_today.py:353`, `views.py:246`,
  `templates/tree/events/journal_added.html`.
- `services/photos/originals.py` decides ownership by stream owner instead of
  `StoryEvent` / S3 key prefix. Upload keys keep `trips/{user_id}/{story_id}/…`.
- `SharedStory` public page unchanged: capability-based, queried by stream.
- Idempotent `ensure_home_entries` SQL run after deploy; invariant test "no event
  without its home entry".

As built (0087–0089):
- The home entry follows the home stream instead of refusing a change: a journal
  entry moved to another thread leaves the old journal and joins the new one; its
  trip membership stays. `Event.save` tracks the stored home stream via `from_db`.
- `Story.add(event)` enforces one trip per event (the database used to, through
  `StoryEvent`'s one-to-one). `Event.trip` and `Event.prefetch_trip()` replace
  `story_entry.story` for the trip badge.
- Photo originals are owned by whoever owns the photo's home stream (the uploader's
  Daily journal), for trip and standalone photos alike; the S3 key prefix is only
  checked on upload now.
- `manage.py ensure_stream_entries` adds home entries for events the previous release
  saved during the deploy (migrations run while it is still serving). Idempotent.
- Checked on the pre-stage-0 production dump: 9,541 home entries, 493 trip entries
  (= the 493 StoryEvent rows), all 16 trips with a stream owned by the traveller.

### Stage 5 — `Event.created_by`
- Nullable → backfill from the home stream's owner → NOT NULL.
- Set at every creation site. `ProjectedOutcome` Made/Redefined/Rescheduled leave the
  model signals for `services/breakthrough` (formset `save(commit=False)`, and the
  admin routed through the service). Services gain a user: `close_observation`,
  `close_board`, `extract_insight`, `migrate_observation_updates_to_journal`.
- `HabitTracked.created_by` derives from the journal entry — do **not** reuse
  `process_journal_entry(user=)`, which means "also tick board tasks".
- Idempotency constraint becomes `(created_by, idempotency_key)`;
  `existing_event()` (`services/photos/events.py`) scopes its lookup to match.

As built (0090–0092):
- Request paths pass the acting user; anything else (projected-outcome events
  created by the `ProjectedOutcome` signals, the admin, Celery) defaults to whoever
  started the event's stream, which is the writer as long as only owners write. The
  signals stay: on the breakthrough page the outcome's owner is the request user, so
  moving them into the service would not change what is recorded. Once editors exist,
  writes on someone else's stream must pass `created_by`.
- `Event.event_stream` and `Event.created_by` are `RESTRICT`: deleting a user works
  when their events are filed under their own threads, and is refused when they are
  filed under someone else's (production has one such observation, from before
  threads had owners).
- The release window: `created_by` becomes required while the previous release still
  serves, so for those seconds that release can't save events.

### Stage 6 — Enforcement
- Queryset methods: `owned_by(user)` and `visible_to(user)` on `Event` (via entries →
  access), `Observation` / `ProjectedOutcome` / `Story` (via their stream), and owner
  filters for `Plan`, `Reflection`, `Board`, `Habit`, `Breakthrough`.
- Scope every view, viewset and service in the tree app (inventory: the endpoint
  table from the exploration — boards, plans, reflections, journal, observations and
  their events, habits, breakthrough, diary, events, stats, today).
- Close the non-obvious leaks: `ComplexPresenter` (`presenters.py`),
  `_validate_event_stream_id`, related-field querysets on write
  (`ObservationUpdatedSerializer.observation`, `forms.py:63`), sidebar counts
  (`templatetags/observation_menu.py`), photo presigning on the today and diary pages.
- Test: one inventory test walks the URL resolver; every route is either in a
  `PUBLIC` allowlist or returns empty/404 for a second user. Unclassified routes fail.

Exit: a second user logs into an empty app. Only now is it safe to create one.

As built:
- `owned_by(user)` / `visible_to(user)` on `Event` (home stream owner / any stream
  membership the user has access to), `Observation`, `ProjectedOutcome`, `Story`
  and `EventStream`. Personal pages (diary, event archive, summaries, daily events)
  and every write use `owned_by`; object pages and observation lists use
  `visible_to`, so sharing needs no further changes to them.
- `ComplexPresenter(stream, user)` shows only attached observations the user can
  access; `is_attached` still answers from the full replay, so an owner can always
  detach. The attach target and `other_event_stream_id` are checked against access
  (no more probing other users' stream ids).
- `test_route_isolation.py` walks every route of the app with every method as a
  second user pointed at the first user's objects: no response may contain the
  first user's data, none may be a server error, and the first user's data must be
  unchanged afterwards. A route with an unknown URL parameter fails the test.
- Checked on the production dump: the owner sees every one of their observations,
  insights, diary entries, plans, reflections, outcomes and trips; the only things
  no longer visible are the other account's observation and its two events.

### Stage 7 — Sharing (view-only)
- `services/streams`: `share(stream, owner, user)`, `revoke(...)`; owner-only.
- UI + API on trip, observation and projected-outcome pages; "shared with me" on the
  trips list, observation lists and the breakthrough year page; shared items render
  read-only and every write path rejects non-owners.
- Not in this stage: editor role, attaching someone else's shared observation to your
  own, Android/CLI surfaces for sharing, user-deletion teardown.

## Critical files
`tasks/apps/tree/models.py`, `signals.py`, `uuid_generators.py`, `serializers.py`,
`forms.py`, `views*.py`, `board_operations.py`, `observation_operations.py`,
`presenters.py`, `services/{today,trips,photos,journalling,breakthrough,observations}`,
`migrations/0028`, `0037`, `0068`, `0074`, `tasks/fixtures/dev/initial_state.json`,
`docker/development/scripts/run-development.sh`. Clients: thread names and
`event_stream_id` stay the API contract, so `cli/` and `android/` need no changes.

## Verification
Per stage, in the dev containers (the local `.tasks-collector.ini` points at
production — do not use the CLI to verify):
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py test`
- `… python manage.py makemigrations --check --dry-run` reports no changes.
- A `MigrationExecutor` test per data migration covering: zero users with seeded
  habits, a closed observation, a journalized dangling attachment, a NULL-thread
  board, two threads with the same slug.
- Migrate a copy of the production dump in dev and compare before/after: event count,
  distinct stream ids, per-type counts; after Stage 4, entries ≥ events.
- Manual, from Stage 1: create a second user in admin, log in as each, confirm the
  today page, board, diary and observation lists; from Stage 6 the second user sees
  nothing of the first; in Stage 7 share a trip and an observation and confirm they
  appear read-only for the second user and disappear on revoke.
