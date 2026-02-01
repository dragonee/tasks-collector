# EventStream model + `created_by` on Event

## Problem

Events use implicit event stream identification via bare UUID fields. There is no single source of truth for stream ownership, no way to share streams between users, and no `created_by` tracking on events. UUID generation logic is scattered across signals and uuid_generators.py.

## Solution

Introduce an explicit `EventStream` model with a single entry point (`request_stream`) for all stream creation. Add `created_by` to both Event and Breakthrough. Migrate all deterministic UUIDs to include user identity.

---

## EventStream model

```python
class EventStreamManager(models.Manager):
    def request_stream(self, user, obj=None, uuid_func=None):
        """Get or create an EventStream. Single entry point for all stream creation."""
        stream_id = uuid_func(user, obj) if uuid_func else uuid.uuid4()
        stream, created = self.get_or_create(
            id=stream_id, defaults={"created_by": user}
        )
        if created:
            stream.users.add(user)
        return stream

class EventStream(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='owned_event_streams'
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='event_streams', blank=True
    )
    objects = EventStreamManager()
```

`request_stream(user, obj, uuid_func)` replaces all current implicit UUID generation:
- Random streams (observations, projected outcomes): `request_stream(user)` -- uuid4
- Deterministic streams (boards, journals, habits): `request_stream(user, obj, uuid_func)` -- uuid5 based on user + entity

---

## Field conversions

Rename `event_stream_id` (UUIDField) to `event_stream` (ForeignKey to EventStream) on all models. Use `db_column='event_stream_id'` to keep the same column name. Django's FK `_id` accessor means `instance.event_stream_id` still returns the UUID everywhere -- most existing code works unchanged.

### Models affected

| Model | Current field | New field |
|-------|--------------|-----------|
| Event | `event_stream_id = UUIDField` | `event_stream = FK(EventStream, CASCADE)` |
| Observation | `event_stream_id = UUIDField(default=uuid4)` | `event_stream = FK(EventStream, CASCADE)` |
| Habit | `event_stream_id = UUIDField(default=uuid4)` | `event_stream = FK(EventStream, CASCADE)` |
| ProjectedOutcome | `event_stream_id = UUIDField(default=uuid4)` | `event_stream = FK(EventStream, CASCADE)` |
| Board | `@property event_stream_id` (computed) | `event_stream = FK(EventStream, CASCADE)` (stored) |
| ObservationAttached | `other_event_stream_id = UUIDField` | `other_event_stream = FK(EventStream, CASCADE, related_name='+')` |
| ObservationDetached | `other_event_stream_id = UUIDField` | `other_event_stream = FK(EventStream, CASCADE, related_name='+')` |

---

## UUID generators -- updated to include user

```python
# uuid_generators.py

def board_stream_uuid(user, board):
    return uuid.uuid5(uuid.NAMESPACE_URL, BOARD_URL.format(user.pk, slugify(board.thread.name)))

def journal_stream_uuid(user, journal_or_thread):
    thread = journal_or_thread.thread if hasattr(journal_or_thread, 'thread_id') else journal_or_thread
    return uuid.uuid5(uuid.NAMESPACE_URL, JOURNAL_URL.format(user.pk, slugify(thread.name)))

def habit_stream_uuid(user, habit):
    obj = habit.habit if hasattr(habit, 'habit_id') else habit
    return uuid.uuid5(uuid.NAMESPACE_URL, HABIT_URL.format(user.pk, slugify(obj.name)))
```

Old functions kept as `_legacy_*` for use in data migrations only.

---

## Signal changes

### Signals removed (replaced by explicit `request_stream` calls in views)

| Signal | Location | Replacement |
|--------|----------|-------------|
| `update_board_committed_event_stream_id` | signals.py:39-42 | `request_stream` in `commit_board()` view |
| `update_habit_tracked_event_stream_id` | signals.py:63-66 | `request_stream` in `track_habit()` view and `process_journal_entry()` |
| `update_journal_added_event_stream_id` | signals.py:113-116 | `request_stream` in `JournalAddedViewSet.perform_create()` |
| `on_habit_name_change_update_event_stream_id` | signals.py:48-60 | Habit rename logic using `request_stream` |

### Signals updated

| Signal | Change |
|--------|--------|
| `copy_observation_to_update_events` (72-86) | Use FK assignment instead of UUID copy |
| `_update_event_stream_id_from_projected_outcome` (137-140) | Use FK assignment |
| `create_initial_projected_outcome_made_event` (122-127) | Derive `created_by` from `instance.event_stream.created_by` |
| `create_projected_outcome_events` (130-134) | Derive `created_by` from `instance.event_stream.created_by` |

---

## Event.created_by

```python
class Event(PolymorphicModel):
    ...
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, editable=False
    )
```

Non-nullable. Set explicitly at every event creation site:

### Views -- pass `request.user`

| View | File:line | Event types created |
|------|-----------|-------------------|
| `commit_board()` | views_board_tasks.py:62 | BoardCommitted |
| `track_habit()` | views_habit.py:84 | HabitTracked |
| `observation_edit()` | views_observation.py:314 | ObservationMade/Recontextualized/Reinterpreted/ReflectedUpon + ObservationUpdated |
| `observation_close()` | views_observation.py:357 | ObservationClosed |
| `observation_attach()` | views_observation.py:447 | ObservationAttached |
| `observation_detach()` | views_observation.py:497 | ObservationDetached |
| `projected_outcome_close()` | views_breakthrough.py:129 | ProjectedOutcomeClosed |
| `projected_outcome_move()` | views_breakthrough.py:157 | ProjectedOutcomeMoved |
| `ObservationViewSet.perform_create()` | views_observation.py:115 | via ObservationSerializer |
| `JournalAddedViewSet.perform_create()` | views.py:57 | JournalAdded |
| `close_observations()` admin action | admin.py:44 | ObservationClosed |

### Services -- `created_by` parameter added

| Service | File | How user is obtained |
|---------|------|---------------------|
| `create_observation_change_events()` | services/observations/event_creation.py | Passed from view/serializer |
| `create_projected_outcome_change_events()` | services/breakthrough/event_creation.py | Passed from signal (derived from `event_stream.created_by`) |
| `process_journal_entry()` | services/journalling/journal_processing.py | From `journal_added.created_by` |
| `migrate_observation_updates_to_journal()` | observation_operations.py | Passed from view |

### Serializer

`ObservationSerializer.save()` (serializers.py:120): gets user from `self.context['request'].user`, passes to `create_observation_change_events()`.

### Factory methods -- `created_by` parameter added

All `from_observation()` and `from_projected_outcome()` static methods on Event subclasses.

---

## Breakthrough.created_by

```python
class Breakthrough(models.Model):
    slug = models.SlugField(max_length=255)  # unique constraint removed
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("slug", "created_by")]
```

Views updated to filter/create by `created_by=request.user`.

---

## Migration sequence

| Migration | Type | Description |
|-----------|------|-------------|
| 0063 | Schema | Create EventStream model + M2M table |
| 0064 | Data | Populate EventStream from all existing distinct UUIDs (Event, Observation, Habit, ProjectedOutcome, ObservationAttached, ObservationDetached) |
| 0065 | Schema | Convert UUIDFields to ForeignKeys (db_column preserves column name). Add Board.event_stream FK, populate from computed property |
| 0066 | Data | Migrate deterministic UUIDs to include user: recompute board/journal/habit UUIDs with user.pk, create new EventStream rows, update all references, delete orphaned streams |
| 0067 | Schema+Data | Add Event.created_by (nullable) -> populate from event_stream.created_by -> make non-nullable |
| 0068 | Schema+Data | Add Breakthrough.created_by (nullable) -> populate -> make non-nullable, alter unique_together |

All data migrations use first superuser (fallback to username 'dragonee' or pk=1).

---

## Files modified

| File | Changes |
|------|---------|
| models.py | EventStream model; field renames on Event, Observation, Habit, ProjectedOutcome, Board, ObservationAttached, ObservationDetached; created_by on Event and Breakthrough; remove Board.event_stream_id property |
| uuid_generators.py | New user-scoped functions, legacy functions for migrations |
| signals.py | Remove 4 handlers, update 4 others |
| serializers.py | ObservationSerializer.save() passes created_by |
| views.py | JournalAddedViewSet uses request_stream |
| views_observation.py | request_stream for new observations, created_by at all creation sites |
| views_habit.py | request_stream + created_by in track_habit |
| views_board_tasks.py | request_stream + created_by in commit_board |
| views_breakthrough.py | created_by filtering on Breakthrough, request_stream |
| admin.py | created_by in close_observations |
| services/observations/event_creation.py | created_by parameter |
| services/breakthrough/event_creation.py | created_by parameter |
| services/journalling/journal_processing.py | derive user from journal_added.created_by |
| observation_operations.py | user parameter |
| migrations/ | 6 new migration files (0063-0068) |
