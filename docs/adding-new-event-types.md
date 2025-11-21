# Adding New Event Types to the Application

This guide describes the step-by-step process for adding new event types to the tasks-collector application. Events are the core of the application's event-sourcing architecture, where all user activities are tracked as polymorphic events with stream IDs.

## Overview

The application uses Django Polymorphic to implement an event-sourcing system. All events inherit from the base `Event` model. Each event type can make use of the following facilities:

- Thread references
- Event streams
- Additional fields defined in child models
- Publication timestamps

The purpose of each of the facilities is described in the sections below. A step-by-step guide to add a new Event type follows.

## TL;DR

1. Decide on event-stream strategy
   1. Thread-based
   2. Entity-based
   3. Unique

## Thread references

Some features, such as task boards and journals are using thread references. For these events, it matters whether they were published under a Daily, Weekly, big-picture or any other thread present in the system.

For example: Weekly summary journal entries will be published with the Weekly thread, making search for these very easy and enabling big-picture (monthly) summaries.

There is no specific action required to enable this behaviour. By default, threads need to be set on all Events, so if you plan not to use this feature, you can default to one value, such as using `Daily` for all events of the new type.

## Event streams

Event streams are unique identifiers marking that the series of events defines one logical entity.

Before creating a new event type, decide on the event stream ID strategy:

### Thread-based Stream ID

Events that belong to a specific thread share the same `event_stream_id` within that thread. These events are considered part of one infinite chronological sequence of events.

The examples of this are `JournalAdded`, `BoardCommitted`, for which all events under a single thread are considered part of the same chronological sequence of events.



### Entity-based streams

Some events belong to a stream connected to a logical entity in the system. 

An example might be a domain aggregate constructed from an `Observation` object and `ObservationMade`, `ObservationUpdated`... events. The lifecycle of the Observation object within the aggregate deletes the Observation instance on the occurrence of the `ObservationClosed` domain event. In their closed state, observations keep track of their events by keeping the same `event_stream_id` on all events.

### Unique / Events that have no external entities

Some events constitute their own logical entities and should have unique event stream ids generated on their own.

An example is a `Discovery` event that is a single event constituting a new connection between other events. 

## Step-by-Step Guide

### 1. Define the Model

Add your new event model to `tasks/apps/tree/models.py`. The model should:

- Inherit from `Event` (and optionally other mixins)
- Define all necessary fields
- Include a `template` attribute pointing to the template file

**Example: Creating a Discovery event**

```python
class Discovery(Event):
    name = models.CharField(max_length=255)
    comment = models.TextField(help_text=_("Discovery details"))

    # ManyToMany to link to arbitrary events
    events = models.ManyToManyField(Event, related_name='discoveries', blank=True)

    template = "tree/events/discovery.html"

    def __str__(self):
        return self.name
```

### 2. Add Signal Handler for event_stream_id

Create a `pre_save` signal handler to set the `event_stream_id` before the event is saved.

#### Thread-based implementation

Use a UUID v5 generator based on thread name. An example would be:

```python
BOARD_URL = 'https://schemas.polybrain.org/tasks/boards/{}'

def thread_event_stream_id(url, thread):
    return uuid.uuid5(uuid.NAMESPACE_URL, name=url.format(slugify(thread.name)))

def board_event_stream_id(board):
    return thread_event_stream_id(BOARD_URL, board.thread)
```

#### Entity-based implementation

The referenced entity typically needs to have `event_stream_id` that can be generated as `uuid.uuid4` random value. Then all the events in this stream would copy this from the referenced object.

```python
# Entity model
class Observation(models.Model):
    # [...]
    event_stream_id = models.UUIDField(default=uuid.uuid4, editable=False)
    # [...]

# Event types
@receiver(pre_save)
def copy_observation_to_update_events(sender, instance, *args, **kwargs):
    if not isinstance(instance, observation_event_types):
        return

    if not instance.thread_id and instance.observation:
        instance.thread_id = instance.observation.thread_id

    instance.event_stream_id = instance.observation.event_stream_id
```

Another way would be to have the first event in the sequence to have a generated event_stream_id and next events would copy the initially generated one.

#### Unique event stream implementation

For such events, you can create a signal that would create a random UUID on creation.

```python
@receiver(pre_save, sender=Discovery)
def update_discovery_event_stream_id(sender, instance, *args, **kwargs):
    # Generate unique event_stream_id for each Discovery if not already set
    if not instance.event_stream_id:
        instance.event_stream_id = uuid.uuid4()
```

### 3. Create Database Migration

Generate and apply the migration:

```bash
# Generate migration
docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py makemigrations

# Apply migration
docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py migrate
```

### 4. Register in Django Admin

Add the event to `tasks/apps/tree/admin.py`:

**Create an admin class:**

```python
class DiscoveryAdmin(PolymorphicChildModelAdmin):
    base_model = Discovery

    list_display = ('__str__', 'name', 'thread', 'published')
    readonly_fields = ('event_stream_id', 'published')
    filter_horizontal = ('events',)  # For ManyToMany fields
```

**Add to EventAdmin.child_models list:**

```python
class EventAdmin(PolymorphicParentModelAdmin):
    base_model = Event

    child_models = [
        HabitTracked,
        BoardCommitted,
        # ... other events ...
        Discovery,  # Add your new event here
        ProjectedOutcomeMade,
        # ... more events ...
    ]
```

**Register the admin:**

```python
admin.site.register(Discovery, DiscoveryAdmin)
```

### 5. Create Template (Optional)

Create a template file referenced in the model's `template` attribute:

```html
<!-- tasks/templates/tree/events/discovery.html -->
<div class="event discovery">
    <h4>{{ event.name }}</h4>
    <p>{{ event.comment }}</p>

    {% if event.events.exists %}
    <div class="related-events">
        <h5>Related Events:</h5>
        <ul>
        {% for related_event in event.events.all %}
            <li>{{ related_event }}</li>
        {% endfor %}
        </ul>
    </div>
    {% endif %}
</div>
```

## Common Patterns and Best Practices

### Foreign Keys to Entities

When linking to entities that can be deleted, use `SET_NULL`:

```python
observation = models.ForeignKey(
    Observation,
    on_delete=models.SET_NULL,
    null=True,
    blank=True
)
```

This preserves the event history even after the entity is deleted.

### Static Factory Methods

Provide factory methods to create events from entities:

```python
@staticmethod
def from_observation(observation, published=None):
    return ObservationMade(
        published=published or aware_from_date(observation.pub_date),
        event_stream_id=observation.event_stream_id,
        thread=observation.thread,
        type=observation.type,
        situation=observation.situation,
        interpretation=observation.interpretation,
        approach=observation.approach,
    )
```

### Mixins for Shared Behavior

Create mixins for common functionality:

```python
class ObservationEventMixin:
    def url(self):
        try:
            observation = Observation.objects.get(event_stream_id=self.event_stream_id)
            return observation.get_absolute_url()
        except Observation.DoesNotExist:
            return reverse('public-observation-closed-detail',
                         kwargs={'event_stream_id': self.event_stream_id})
```

### Automatic Event Creation

Use `post_save` signals to automatically create events when entities are created or modified:

```python
@receiver(post_save, sender=ProjectedOutcome)
def create_initial_projected_outcome_made_event(sender, instance, created, **kwargs):
    if created:
        event = ProjectedOutcomeMade.from_projected_outcome(instance)
        event.save()
```

## Testing Your Event Type

After creating a new event type:

1. **Test in Django Admin:**
   - Navigate to the admin interface
   - Create a new instance of your event
   - Verify all fields save correctly
   - Check that `event_stream_id` is set properly

2. **Test via Django Shell:**
   ```python
   from tasks.apps.tree.models import Discovery, Thread

   thread = Thread.objects.first()
   discovery = Discovery.objects.create(
       name="Test Discovery",
       comment="This is a test",
       thread=thread
   )

   print(f"Event Stream ID: {discovery.event_stream_id}")
   print(f"Discovery: {discovery}")
   ```

3. **Verify in Event List:**
   - Check that your event appears in the Event admin list
   - Verify it's correctly categorized as the child type
   - Test filtering and searching

## Related Files

When adding a new event type, you'll typically modify:

- `tasks/apps/tree/models.py` - Model definition and signals
- `tasks/apps/tree/uuid_generators.py` - UUID generators (if thread-based)
- `tasks/apps/tree/admin.py` - Admin registration
- `tasks/templates/tree/events/*.html` - Event template (optional)
- `tasks/apps/tree/migrations/*.py` - Generated migration files

## Examples in Codebase

For reference, examine these existing event types:

- **Simple event with thread-based ID:** `JournalAdded` (lines 522-532 in models.py)
- **Entity with unique ID and related events:** `Observation` (lines 265-322 in models.py)
- **Event with entity-based ID:** `ObservationMade` (lines 373-402 in models.py)
- **Event with ManyToMany relationships:** `Discovery` (lines 535-550 in models.py)
- **Complex event with change tracking:** `ProjectedOutcomeRedefined` (lines 692-716 in models.py)
