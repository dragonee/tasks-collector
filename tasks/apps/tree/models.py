import secrets
import uuid
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.text import Truncator, slugify
from django.utils.translation import gettext_lazy as _

from polymorphic.managers import PolymorphicManager
from polymorphic.models import PolymorphicModel
from polymorphic.query import PolymorphicQuerySet

from .services.boards import items as board_items
from .services.progress import parse_progress
from .utils.datetime import aware_from_date
from .utils.strings import coalesce


def empty_dict():
    return {}


def default_state():
    return []


class EventStreamQuerySet(models.QuerySet):
    def owned_by(self, user):
        return self.filter(access__user=user, access__role=EventStreamAccess.Role.OWNER)

    def visible_to(self, user):
        """Streams ``user`` has any access to (owns, or was shared)."""
        return self.filter(access__user=user)


class EventStreamManager(models.Manager.from_queryset(EventStreamQuerySet)):
    def create_for(self, user, type):
        """A new stream of ``type`` created by and owned by ``user``."""
        with transaction.atomic():
            stream = self.create(type=type, created_by=user)
            EventStreamAccess.objects.create(
                stream=stream, user=user, role=EventStreamAccess.Role.OWNER
            )
        return stream


class EventStream(models.Model):
    """A sequence of events about one thing: a thread's board or journal, a
    habit, an observation, a projected outcome.

    Streams are reached from what they are about (``Thread.journal_stream``,
    ``Observation.event_stream``...), never computed. Who may see a stream is
    its access list (``EventStreamAccess``).
    """

    class Type(models.TextChoices):
        BOARD = "board", _("Board")
        JOURNAL = "journal", _("Journal")
        HABIT = "habit", _("Habit")
        OBSERVATION = "observation", _("Observation")
        PROJECTED_OUTCOME = "projected_outcome", _("Projected outcome")
        TRIP = "trip", _("Trip")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=32, choices=Type.choices)

    # Who started the stream; provenance only. Permissions come from access.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_event_streams",
    )
    created = models.DateTimeField(default=timezone.now)

    objects = EventStreamManager()

    def __str__(self):
        return f"{self.get_type_display()} {self.id}"


class EventStreamAccess(models.Model):
    """A user's access to a whole stream. Every stream has exactly one
    owner; sharing adds viewers (read only) or, for boards, editors (read and
    change)."""

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        EDITOR = "editor", _("Editor")
        VIEWER = "viewer", _("Viewer")

    WRITE_ROLES = (Role.OWNER, Role.EDITOR)

    stream = models.ForeignKey(
        EventStream, on_delete=models.CASCADE, related_name="access"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stream_access",
    )
    role = models.CharField(max_length=16, choices=Role.choices)

    class Meta:
        verbose_name_plural = "Event stream access"
        constraints = [
            models.UniqueConstraint(
                fields=["stream", "user"], name="eventstreamaccess_stream_user_unique"
            ),
            models.UniqueConstraint(
                fields=["stream"],
                condition=models.Q(role="owner"),
                name="eventstreamaccess_one_owner_per_stream",
            ),
        ]

    def __str__(self):
        return f"{self.user} {self.role} of {self.stream}"


class ThreadQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def daily(self, user):
        """``user``'s Daily thread, where diary-style entries land."""
        return self.get(user=user, name=Thread.DAILY)

    def board_editable_by(self, user):
        """Threads whose board ``user`` may change: their own, and the boards
        shared with them as editor. Their own come first, so a name they share
        with a shared board finds their own."""
        return self.filter(
            board_stream__access__user=user,
            board_stream__access__role__in=EventStreamAccess.WRITE_ROLES,
        ).order_by(
            models.Case(models.When(user=user, then=0), default=1),
            "name",
        )


class Thread(models.Model):
    # Every user gets the built-in threads (see services.provisioning) and
    # cannot delete them: code looks them up by these names.
    DAILY = "Daily"
    WEEKLY = "Weekly"
    BIG_PICTURE = "big-picture"
    BUILTIN_NAMES = (DAILY, WEEKLY, BIG_PICTURE)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="threads"
    )

    # readonly-once-set
    # if you need to change name, a migration needs to be run
    name = models.CharField(max_length=255)

    # Board commits and journal entries filed under the thread; both are
    # created with the thread. RESTRICT: a stream can't be deleted while its
    # thread exists, but both go when their user is deleted.
    board_stream = models.OneToOneField(
        EventStream,
        on_delete=models.RESTRICT,
        related_name="board_thread",
        editable=False,
    )
    journal_stream = models.OneToOneField(
        EventStream,
        on_delete=models.RESTRICT,
        related_name="journal_thread",
        editable=False,
    )

    objects = ThreadQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self.board_stream_id is None:
            self.board_stream = EventStream.objects.create_for(
                self.user, EventStream.Type.BOARD
            )
        if self.journal_stream_id is None:
            self.journal_stream = EventStream.objects.create_for(
                self.user, EventStream.Type.JOURNAL
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def is_builtin(self):
        return self.name in self.BUILTIN_NAMES

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"], name="thread_user_name_unique"
            ),
        ]


class EventQuerySet(PolymorphicQuerySet):
    def owned_by(self, user):
        """Events whose home stream ``user`` owns: their diary, boards, habits,
        observations and outcomes. What personal pages list."""
        return self.filter(
            event_stream__access__user=user,
            event_stream__access__role=EventStreamAccess.Role.OWNER,
        )

    def visible_to(self, user):
        """Events in any stream ``user`` can access, home or not: their own
        plus what was shared with them."""
        return self.filter(
            models.Exists(
                EventStreamEntry.objects.filter(
                    event=models.OuterRef("pk"), stream__access__user=user
                )
            )
        )


class Event(PolymorphicModel):
    published = models.DateTimeField(default=timezone.now)

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)

    # The stream the event belongs to (its home). Same column as the old
    # event_stream_id UUID. RESTRICT: a stream goes only after its events, or
    # together with them when their user is deleted.
    # No index of its own: the (event_stream_id, published) one leads with it.
    event_stream = models.ForeignKey(
        EventStream,
        on_delete=models.RESTRICT,
        related_name="events",
        db_column="event_stream_id",
        db_index=False,
        editable=False,
    )

    # Optional client-supplied key for exactly-once creation. When a device
    # retries a write whose response was lost (e.g. an offline outbox), the
    # service re-uses the existing event instead of creating a duplicate. A
    # transport concern, deliberately on the generic Event base so any
    # event-creating endpoint can opt in — not just trip notes/photos.
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)

    # Who wrote the event. Provenance only: what someone may see or change is
    # decided by stream access, never by this. Defaults to whoever started the
    # event's stream (see save); writes on behalf of a user pass it explicitly.
    # Null once the writer is deleted: an editor's commits stay on the board
    # they shared, which isn't theirs to take with them.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_events",
        editable=False,
    )

    objects = PolymorphicManager.from_queryset(EventQuerySet)()

    class Meta:
        indexes = [
            models.Index(fields=["published"]),
            models.Index(fields=["event_stream_id", "published"]),
        ]

        ordering = ("published",)

        constraints = [
            # Partial unique constraint: only opted-in rows are indexed, so the
            # hot tree_event table pays nothing for the rows that don't set a
            # key. Scoped to the writer: one user's key can never collide with
            # (or reveal) another user's event.
            models.UniqueConstraint(
                fields=["created_by", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="event_created_by_idempotency_key_unique",
            ),
        ]

    def __str__(self):
        return "[{cls}] #{pk}".format(
            cls=self.get_real_instance_class().__name__, pk=self.pk
        )

    def derived_event_stream_id(self):
        """The id of the stream this event belongs to, when it follows from
        what the event is about (its thread, habit, observation...).

        None means the creator sets ``event_stream_id`` itself (the
        ``from_observation``-style factories do).
        """
        return None

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        # The home stream as stored, so save() can tell when it changes.
        instance._stored_event_stream_id = instance.__dict__.get("event_stream_id")
        return instance

    def save(self, *args, **kwargs):
        derived = self.derived_event_stream_id()
        if derived is not None:
            self.event_stream_id = derived
        if self.event_stream_id is None:
            raise ValueError(
                f"{type(self).__name__} needs an event_stream_id: nothing it is "
                "about determines its stream."
            )

        if self._state.adding and self.created_by_id is None:
            # Nobody acting on another's behalf: the stream's own user wrote it.
            # Only on insert: a writer who was deleted stays unknown.
            self.created_by_id = (
                EventStream.objects.filter(pk=self.event_stream_id)
                .values_list("created_by", flat=True)
                .get()
            )

        stored = None if self._state.adding else self._stored_event_stream_id
        with transaction.atomic():
            super().save(*args, **kwargs)
            # The event is a member of its home stream, and stays one when the
            # home changes (a journal entry moved to another thread).
            if stored != self.event_stream_id:
                if stored is not None:
                    EventStreamEntry.objects.filter(
                        event_id=self.pk, stream_id=stored
                    ).delete()
                EventStreamEntry.objects.get_or_create(
                    event_id=self.pk, stream_id=self.event_stream_id
                )
        self._stored_event_stream_id = self.event_stream_id

    _stored_event_stream_id = None

    @property
    def trip(self):
        """The trip (Story) this event was added to, or None.

        Reads ``trip_entries`` when the queryset was prefetched with
        ``Event.prefetch_trip()``; otherwise costs one query.
        """
        entries = getattr(self, "trip_entries", None)
        if entries is None:
            entries = list(
                self.stream_entries.filter(
                    stream__type=EventStream.Type.TRIP
                ).select_related("stream__story")
            )
        return entries[0].stream.story if entries else None

    @staticmethod
    def prefetch_trip():
        """Prefetch for ``trip`` on a list of events (one query for all)."""
        return models.Prefetch(
            "stream_entries",
            queryset=EventStreamEntry.objects.filter(
                stream__type=EventStream.Type.TRIP
            ).select_related("stream__story"),
            to_attr="trip_entries",
        )

    @staticmethod
    def prefetch_related_by_kind(events, lookups):
        """``prefetch_related_objects`` for a list of events of mixed kinds,
        where only some kinds have the relation, which ``prefetch_related``
        can't do. ``lookups`` maps an event class to the lookups to prefetch
        on the events of that class or its subclasses."""
        for kind, kind_lookups in lookups.items():
            models.prefetch_related_objects(
                [event for event in events if isinstance(event, kind)], *kind_lookups
            )


class EventStreamEntry(models.Model):
    """An event's membership in a stream.

    Every event is a member of its home stream (``Event.event_stream``, kept
    by ``Event.save``) and may be added to others: a trip note is in its
    thread's journal and in the trip.
    """

    stream = models.ForeignKey(
        EventStream, on_delete=models.CASCADE, related_name="entries"
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="stream_entries"
    )
    added = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Event stream entries"
        constraints = [
            models.UniqueConstraint(
                fields=["stream", "event"], name="eventstreamentry_stream_event_unique"
            ),
        ]

    def __str__(self):
        return f"{self.stream} <- event #{self.event_id}"


class BoardCommitted(Event):
    # thread set manually from board

    focus = models.CharField(max_length=255)

    before = models.JSONField(default=default_state)
    after = models.JSONField(default=default_state)

    transitions = models.JSONField(default=empty_dict)

    date_started = models.DateTimeField(default=timezone.now)

    @property
    def date_closed(self):
        return self.published

    def derived_event_stream_id(self):
        return self.thread.board_stream_id


class Habit(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="habits"
    )

    # Display name
    name = models.CharField(max_length=255)

    # URL Slug, unique per user
    slug = models.SlugField(max_length=255)

    # Same column as the old event_stream_id UUID, so ids keep working.
    event_stream = models.OneToOneField(
        EventStream,
        on_delete=models.RESTRICT,
        related_name="habit",
        db_column="event_stream_id",
        editable=False,
    )

    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug"], name="habit_user_slug_unique"
            ),
        ]

    def save(self, *args, **kwargs):
        if self.event_stream_id is None:
            self.event_stream = EventStream.objects.create_for(
                self.user, EventStream.Type.HABIT
            )
        super().save(*args, **kwargs)

    def as_hashtags(self):
        return ["#{}".format(keyword) for keyword in self.get_keywords()]

    def get_keywords(self):
        """Get all keywords for this habit as a set. Reads ``keywords.all()``,
        so a list of habits can prefetch them: ``prefetch_related("keywords")``."""
        return {keyword.keyword for keyword in self.keywords.all()}


class HabitKeyword(models.Model):
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name="keywords")

    # Always the habit's owner (set on save): it lets a keyword be unique per
    # user, which a constraint can't express through the habit relation.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="habit_keywords",
        editable=False,
    )

    keyword = models.SlugField(max_length=255, allow_unicode=True)

    class Meta:
        ordering = ("keyword",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "keyword"], name="habitkeyword_user_keyword_unique"
            ),
        ]

    def save(self, *args, **kwargs):
        self.user_id = self.habit.user_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.habit.name}: {self.keyword}"


class HabitTracked(Event):
    # thread must be set manually

    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)

    occured = models.BooleanField(default=True)

    note = models.TextField(null=True, blank=True)

    template = "tree/events/habit_tracked.html"

    def derived_event_stream_id(self):
        return self.habit.event_stream_id

    def __str__(self):
        return "{} {}".format(self.habit, self.published)


class BoardQuerySet(models.QuerySet):
    def editable_by(self, user):
        """Boards ``user`` may read and change: the boards of their own threads
        and the boards shared with them (see ``Thread.board_editable_by``)."""
        return self.filter(
            thread__board_stream__access__user=user,
            thread__board_stream__access__role__in=EventStreamAccess.WRITE_ROLES,
        )


class Board(models.Model):
    date_started = models.DateTimeField(default=timezone.now)

    state = models.JSONField(default=default_state, blank=True)

    focus = models.CharField(max_length=255, null=True, blank=True)

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)

    objects = BoardQuerySet.as_manager()

    class Meta:
        ordering = ("-date_started",)

    def save(self, *args, **kwargs):
        # Whoever wrote the tree (the web board, the Android app, a commit),
        # its items are stored in one shape.
        board_items.normalise(self.state)
        super().save(*args, **kwargs)

    def __str__(self):
        if not self.focus:
            return str(self.thread)

        return "{} {}".format(self.focus, self.thread)


class Reflection(models.Model):
    """What went well in a period, what could go better, and what would be
    best: three lists of lines (``ReflectionLine``)."""

    pub_date = models.DateField()

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)

    class Meta:
        ordering = ("-pub_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "pub_date"], name="reflection_thread_pub_date_unique"
            ),
        ]

    def __str__(self):
        return "{} ({})".format(self.pub_date, self.thread)

    def text(self, field):
        """The lines of ``field`` (good, better, best) as text, one to a
        line."""
        if self.pk is None:
            return ""
        return "\n".join(
            line.content for line in self.lines.all() if line.field == field
        )

    @property
    def good(self):
        """What went well."""
        return self.text("good")

    @property
    def better(self):
        """What could be done better."""
        return self.text("better")

    @property
    def best(self):
        """What the best version of oneself would do."""
        return self.text("best")


class Plan(models.Model):
    """What is to be done in a period: a list of lines (``PlanLine``), most
    of them tasks."""

    pub_date = models.DateField()

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)

    class Meta:
        ordering = ("-pub_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "pub_date"], name="plan_thread_pub_date_unique"
            ),
        ]

    def __str__(self):
        return "{} ({})".format(self.pub_date, self.thread)

    @property
    def focus(self):
        """The plan as text, one line to a line."""
        if self.pk is None:
            return ""
        return "\n".join(line.content for line in self.lines.all())


class ObservationType(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    color = models.CharField(
        max_length=7,
        default="#ca8911",
        help_text=_("Color in hex format (e.g., #FF5733)"),
    )

    def __str__(self):
        return self.name


class ObservationQuerySet(models.QuerySet):
    def owned_by(self, user):
        return self.filter(user=user)

    def visible_to(self, user):
        """Observations ``user`` can access (theirs, or shared with them)."""
        return self.filter(event_stream__access__user=user)

    def with_last_event_published(self):
        """Annotate queryset with the last event published date"""
        from django.db.models import OuterRef, Subquery

        last_event_subquery = (
            Event.objects.filter(event_stream_id=OuterRef("event_stream_id"))
            .order_by("-published")
            .values("published")[:1]
        )

        return self.annotate(last_event_published=Subquery(last_event_subquery))

    def with_attached_count(self):
        """
        Annotate each observation with ``attached_count``: the number of
        observations currently attached to it (i.e. how "complex" it is).

        Mirrors ComplexPresenter's latest-event-wins replay in SQL: an
        ObservationAttached row represents a currently-attached pair only when
        no later attach and no later-or-equal detach exist for the same
        (event_stream_id, other_event_stream_id) pair. Counting the distinct
        surviving pairs in one correlated subquery avoids a per-row presenter.
        """
        from django.db.models import Count, Exists, OuterRef, Subquery
        from django.db.models.functions import Coalesce

        later_attach = ObservationAttached.objects.filter(
            event_stream_id=OuterRef("event_stream_id"),
            other_event_stream_id=OuterRef("other_event_stream_id"),
            published__gt=OuterRef("published"),
        )
        later_or_equal_detach = ObservationDetached.objects.filter(
            event_stream_id=OuterRef("event_stream_id"),
            other_event_stream_id=OuterRef("other_event_stream_id"),
            published__gte=OuterRef("published"),
        )

        currently_attached = (
            ObservationAttached.objects.filter(
                event_stream_id=OuterRef("event_stream_id")
            )
            .annotate(
                superseded_by_attach=Exists(later_attach),
                superseded_by_detach=Exists(later_or_equal_detach),
            )
            .filter(superseded_by_attach=False, superseded_by_detach=False)
            .order_by()
            .values("event_stream_id")
            .annotate(count=Count("other_event_stream_id", distinct=True))
            .values("count")
        )

        return self.annotate(attached_count=Coalesce(Subquery(currently_attached), 0))


class ObservationManager(models.Manager.from_queryset(ObservationQuerySet)):
    pass


class Observation(models.Model):
    pub_date = models.DateField()

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)
    type = models.ForeignKey(ObservationType, on_delete=models.CASCADE)

    # Outlives the observation: closing deletes the row, the stream stays.
    # Same column as the old event_stream_id UUID, so ids keep working.
    event_stream = models.OneToOneField(
        EventStream,
        on_delete=models.RESTRICT,
        related_name="observation",
        db_column="event_stream_id",
        editable=False,
    )

    objects = ObservationManager()

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    interpretation = models.TextField(
        help_text=_("How you saw it, what you felt?"), null=True, blank=True
    )
    approach = models.TextField(
        help_text=_("How should you approach it in the future?"), null=True, blank=True
    )

    class Meta:
        ordering = ("-pub_date", "-pk")

    def __str__(self):
        return "{}: {} ({})".format(
            self.pub_date, Truncator(self.situation).words(6), self.thread
        )

    def save(self, *args, **kwargs):
        if self.event_stream_id is None:
            self.event_stream = EventStream.objects.create_for(
                self.user, EventStream.Type.OBSERVATION
            )
        super().save(*args, **kwargs)

    def copy(self, as_new=True):
        kwargs = {}

        if not as_new:
            kwargs["pk"] = self.pk
            kwargs["event_stream_id"] = self.event_stream_id

        return Observation(
            pub_date=self.pub_date,
            thread_id=self.thread_id,
            type_id=self.type_id,
            user_id=self.user_id,
            situation=self.situation,
            interpretation=self.interpretation,
            approach=self.approach,
            **kwargs,
        )

    def situation_truncated(self):
        return Truncator(self.situation).words(6)

    def get_events(self):
        if not self.event_stream_id:
            return Event.objects.none()

        return Event.objects.filter(event_stream_id=self.event_stream_id)

    def get_absolute_url(self):
        return reverse("public-observation-edit", kwargs={"observation_id": self.pk})


class ObservationPropertyEventMixin:
    @property
    def observation(self):
        return Observation.objects.get(event_stream_id=self.event_stream_id)


class ObservationEventMixin:
    """An event in an observation's stream. A list of them can load what they
    look up about their observation for all of them at once:
    ``prefetch_open_observation`` and ``prefetch_situations``."""

    @staticmethod
    def _in(events):
        return [event for event in events if isinstance(event, ObservationEventMixin)]

    @cached_property
    def open_observation(self):
        """The event's observation while it is open, None once it is closed."""
        return Observation.objects.filter(event_stream_id=self.event_stream_id).first()

    @staticmethod
    def prefetch_open_observation(events):
        """Look up ``open_observation`` for the observation events among
        ``events`` in one query."""
        events = ObservationEventMixin._in(events)
        observations = {
            observation.event_stream_id: observation
            for observation in Observation.objects.filter(
                event_stream_id__in={event.event_stream_id for event in events}
            )
        }
        for event in events:
            event.open_observation = observations.get(event.event_stream_id)

    def url(self):
        if self.open_observation is not None:
            return self.open_observation.get_absolute_url()
        return reverse(
            "public-observation-closed-detail",
            kwargs={"event_stream_id": self.event_stream_id},
        )

    @cached_property
    def situations(self):
        """(published, situation) of each event that set the observation's
        situation (made, recontextualized), oldest first."""
        return _situations_by_stream({self.event_stream_id})[self.event_stream_id]

    @staticmethod
    def prefetch_situations(events):
        """Look up ``situations`` for the observation events among ``events``
        in one query per kind of event."""
        events = ObservationEventMixin._in(events)
        situations = _situations_by_stream({event.event_stream_id for event in events})
        for event in events:
            event.situations = situations[event.event_stream_id]

    def situation(self):
        ### XXX Situation at the time of the event or current?
        ### For now, current is implemented here
        if not self.situations:
            raise Observation.DoesNotExist

        return self.situations[-1][1]

    def situation_at_creation(self):
        earlier = [
            situation
            for published, situation in self.situations
            if published <= self.published
        ]

        if not earlier:
            raise Observation.DoesNotExist

        return earlier[-1]


def _situations_by_stream(stream_ids):
    """(published, situation) of the made and recontextualized events of each
    of ``stream_ids``, oldest first; an empty list for a stream without any."""
    situations = defaultdict(list)
    events = (
        Event.objects.instance_of(ObservationMade, ObservationRecontextualized)
        .filter(event_stream_id__in=stream_ids)
        .order_by("published")
    )
    for event in events:
        situations[event.event_stream_id].append((event.published, event.situation))
    return situations


class ObservationMade(Event, ObservationEventMixin, ObservationPropertyEventMixin):
    # event_stream_id <- Observation
    # thread <- Observation (can be updated)

    type = models.ForeignKey(ObservationType, on_delete=models.CASCADE)

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    interpretation = models.TextField(
        help_text=_("How you saw it, what you felt?"), null=True, blank=True
    )
    approach = models.TextField(
        help_text=_("How should you approach it in the future?"), null=True, blank=True
    )

    template = "tree/events/observation_made.html"

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

    def __str__(self):
        return "{}: {} ({})".format(
            self.published, Truncator(self.situation).words(6), self.thread
        )


class ObservationUpdated(Event, ObservationEventMixin):
    observation = models.ForeignKey(
        Observation, on_delete=models.SET_NULL, null=True, blank=True
    )

    template = "tree/events/observation_updated.html"

    comment = models.TextField(help_text=_("Update"))

    def derived_event_stream_id(self):
        # The FK is cleared when the observation closes; the stream stays.
        return self.observation.event_stream_id if self.observation_id else None

    def save(self, *args, **kwargs):
        # Updates added in the observation form or the admin inherit its thread.
        if not self.thread_id and self.observation_id:
            self.thread_id = self.observation.thread_id
        super().save(*args, **kwargs)

    def __str__(self):
        return self.comment


class ObservationRecontextualized(
    Event, ObservationEventMixin, ObservationPropertyEventMixin
):
    old_situation = models.TextField(blank=True)
    situation = models.TextField()

    template = "tree/events/observation_recontextualized.html"

    @staticmethod
    def from_observation(observation, old, published=None):
        return ObservationRecontextualized(
            published=published or timezone.now(),
            event_stream_id=observation.event_stream_id,
            thread=observation.thread,
            old_situation=coalesce(old),
            situation=coalesce(observation.situation),
        )


class ObservationReinterpreted(
    Event, ObservationEventMixin, ObservationPropertyEventMixin
):
    old_interpretation = models.TextField(blank=True)
    interpretation = models.TextField()

    template = "tree/events/observation_reinterpreted.html"

    @staticmethod
    def from_observation(observation, old, published=None):
        return ObservationReinterpreted(
            published=published or timezone.now(),
            event_stream_id=observation.event_stream_id,
            thread=observation.thread,
            old_interpretation=coalesce(old),
            interpretation=coalesce(observation.interpretation),
        )


class ObservationReflectedUpon(
    Event, ObservationEventMixin, ObservationPropertyEventMixin
):
    old_approach = models.TextField(blank=True)
    approach = models.TextField()

    template = "tree/events/observation_reflectedupon.html"

    @staticmethod
    def from_observation(observation, old, published=None):
        return ObservationReflectedUpon(
            published=published or timezone.now(),
            event_stream_id=observation.event_stream_id,
            thread=observation.thread,
            old_approach=coalesce(old),
            approach=coalesce(observation.approach),
        )


class ObservationClosed(Event, ObservationEventMixin, ObservationPropertyEventMixin):
    type = models.ForeignKey(ObservationType, on_delete=models.CASCADE)

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    interpretation = models.TextField(
        help_text=_("How you saw it, what you felt?"), null=True, blank=True
    )
    approach = models.TextField(
        help_text=_("How should you approach it in the future?"), null=True, blank=True
    )

    template = "tree/events/observation_closed.html"

    def situation_truncated(self):
        return Truncator(self.situation).words(6)

    def get_absolute_url(self):
        return reverse(
            "public-observation-closed-detail",
            kwargs={"event_stream_id": self.event_stream_id},
        )

    @staticmethod
    def from_observation(observation, published=None):
        return ObservationClosed(
            published=published or timezone.now(),
            event_stream_id=observation.event_stream_id,
            thread=observation.thread,
            type=observation.type,
            situation=observation.situation,
            interpretation=observation.interpretation,
            approach=observation.approach,
        )


class InsightRefined(Event, ObservationEventMixin):
    type = models.ForeignKey(ObservationType, on_delete=models.CASCADE)

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    approach = models.TextField(
        help_text=_("How should you approach it in the future?"), null=True, blank=True
    )

    template = "tree/events/insight_refined.html"

    @staticmethod
    def from_observation_closed(
        observation_closed, situation=None, approach=None, published=None
    ):
        return InsightRefined(
            published=published or timezone.now(),
            event_stream_id=observation_closed.event_stream_id,
            thread=observation_closed.thread,
            type=observation_closed.type,
            situation=(
                situation if situation is not None else observation_closed.situation
            ),
            approach=approach if approach is not None else observation_closed.approach,
        )

    def __str__(self):
        return "{}: {} ({})".format(
            self.published, Truncator(self.situation).words(6), self.thread
        )


observation_event_types = (
    ObservationMade,
    ObservationClosed,
    ObservationRecontextualized,
    ObservationReflectedUpon,
    ObservationReinterpreted,
    ObservationUpdated,
)


class JournalAdded(Event):
    comment = models.TextField(help_text=_("Update"))

    template = "tree/events/journal_added.html"

    # Lets templates branch on plain vs. photo entries without isinstance.
    # PhotoAdded overrides this to True.
    is_photo = False

    def derived_event_stream_id(self):
        return self.thread.journal_stream_id

    def __str__(self):
        return self.comment


class PhotoAdded(JournalAdded):
    """A journal entry that carries a photo stored in S3.

    Subclasses JournalAdded so the comment flows through
    ``process_journal_entry`` unchanged (habit/POI extraction) and the
    event is picked up by the existing trip ``get_detail`` query. The
    original is uploaded directly to S3 by the client; ``thumbnail_key``
    stays null until the Celery thumbnail task fills it.
    """

    original_key = models.CharField(max_length=512)
    thumbnail_key = models.CharField(max_length=512, null=True, blank=True)
    content_type = models.CharField(max_length=100)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    # Hex SHA-256 of the original bytes, supplied by the client. Drives
    # per-trip dedup (see services.trips.add_trip_photo) so re-picking the same
    # image doesn't create a second photo. Plain (non-unique) index on purpose:
    # dedup is scoped to a Story, so the same image may legitimately appear in
    # more than one trip. Null on legacy rows and standalone photos.
    content_hash = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    template = "tree/events/journal_added.html"

    is_photo = True


class JournalTag(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journal_tags"
    )

    name = models.CharField(max_length=255)

    # Unique per user
    slug = models.SlugField(max_length=255)

    journals = models.ManyToManyField(JournalAdded, related_name="tags", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug"], name="journaltag_user_slug_unique"
            ),
        ]

    def __str__(self):
        return self.name


class TaskQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Tasks ``user`` can see: those of the boards they have access to."""
        return self.filter(event_stream__access__user=user)

    def editable_by(self, user):
        """Tasks ``user`` may plan, complete and rename: those of their own
        boards and of the boards shared with them to edit."""
        return self.filter(
            event_stream__access__user=user,
            event_stream__access__role__in=EventStreamAccess.WRITE_ROLES,
        )


class Task(models.Model):
    """Something planned: for a day, a week, a month.

    A board item is an unscheduled task and has no row here. Planning it, or
    writing a line into a plan, makes the task; the plans it is on are its
    ``plan_lines``. It stays once it is done.

    A task lives in the stream of a board (``Thread.board_stream``): the
    board its item is on, or its maker's default board when it was typed
    into a plan. Whoever has access to that board has access to the task.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who made it. Provenance only, like Event.created_by: access is the
    # stream's.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks"
    )

    # May carry a step counter, "Do x (3)": see ``total``.
    text = models.TextField()

    # Steps done. One for a plain task that is done; may pass ``total``.
    done_count = models.PositiveIntegerField(default=0)
    # When ``done_count`` reached ``total``; None while the task is open.
    completed_at = models.DateTimeField(null=True, blank=True)

    created = models.DateTimeField(default=timezone.now)

    # Short name of the task inside plan and reflection text: a line ending
    # with "^t<anchor>" is this task's, whatever its wording.
    anchor = models.CharField(max_length=8, unique=True, editable=False)

    # The board item the task was planned from, if any, and still is on.
    board = models.ForeignKey(
        "Board", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    board_item_id = models.CharField(max_length=64, null=True, blank=True)

    # CASCADE: when a board's stream goes (with its owner), so do the tasks
    # others made on it.
    event_stream = models.ForeignKey(
        EventStream, on_delete=models.CASCADE, related_name="tasks", editable=False
    )

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ("created",)

    def __str__(self):
        return self.text

    def save(self, *args, **kwargs):
        if not self.anchor:
            self.anchor = secrets.token_hex(4)
            while Task.objects.filter(anchor=self.anchor).exists():
                self.anchor = secrets.token_hex(4)
        super().save(*args, **kwargs)

    @property
    def total(self):
        """How many steps the task has: the counter in its text, else one."""
        progress = parse_progress(self.text)
        return progress.total if progress else 1

    @property
    def done(self):
        return self.done_count >= self.total


class PlanLineManager(models.Manager):
    """Plan lines come with their task: what a line says is its task's
    text."""

    def get_queryset(self):
        return super().get_queryset().select_related("task")


class PlanLine(models.Model):
    """A line of a plan, in order.

    A line with a task shows the task's text, so the task reads the same on
    every plan it is on. A line without one is plain text: what was written
    before tasks had rows, a separator, a line on a thread that plans no
    tasks.
    """

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveIntegerField()

    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, null=True, blank=True, related_name="plan_lines"
    )
    text = models.TextField(blank=True, default="")

    objects = PlanLineManager()

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "task"], name="planline_plan_task_unique"
            ),
        ]

    def __str__(self):
        return self.content

    @property
    def content(self):
        return self.task.text if self.task_id else self.text


class ReflectionLine(models.Model):
    """A line of one of a reflection's three fields, in order.

    The wording is the line's own. A line written when a task was completed
    stays linked to the task however it is reworded; other lines have no
    task.
    """

    class Field(models.TextChoices):
        GOOD = "good", _("Good")
        BETTER = "better", _("Better")
        BEST = "best", _("Best")

    reflection = models.ForeignKey(
        Reflection, on_delete=models.CASCADE, related_name="lines"
    )
    field = models.CharField(max_length=8, choices=Field.choices)
    position = models.PositiveIntegerField()

    text = models.TextField(blank=True, default="")

    task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reflection_lines",
    )
    completion = models.ForeignKey(
        "TaskCompleted",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reflection_lines",
    )

    class Meta:
        ordering = ("position", "pk")

    def __str__(self):
        return self.text

    @property
    def content(self):
        return self.text


class TaskCompleted(Event):
    """A step of a task was done: the whole task, or one of its counted
    steps. Undoing it deletes the event."""

    # event_stream_id <- Task
    # thread <- the thread of the task's board

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="completions")

    # The day it was done on for whoever did it; ``published`` is the moment.
    day = models.DateField()

    # The task's text when it was done, with the step reached: "Do x (2)".
    text = models.TextField()

    # The note written with it, if any.
    journal = models.ForeignKey(
        JournalAdded, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    template = "tree/events/task_completed.html"

    def derived_event_stream_id(self):
        return self.task.event_stream_id

    def __str__(self):
        return self.text


class Breakthrough(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="breakthroughs",
    )

    # The year, unique per user.
    slug = models.SlugField(max_length=255)

    published = models.DateTimeField(default=timezone.now)
    last_updated = models.DateTimeField(auto_now=True)

    areas_of_concern = models.TextField(
        _("Areas of concern"),
        help_text=_("List areas of life thet give you most discomfort"),
    )

    theme = models.CharField(
        _("Theme of the year"),
        max_length=255,
        help_text=_("A phrase that captures your year"),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug"], name="breakthrough_user_slug_unique"
            ),
        ]


class ProjectedOutcomeQuerySet(models.QuerySet):
    def owned_by(self, user):
        return self.filter(breakthrough__user=user)

    def visible_to(self, user):
        """Outcomes ``user`` can access (theirs, or shared with them)."""
        return self.filter(event_stream__access__user=user)


class ProjectedOutcome(models.Model):
    breakthrough = models.ForeignKey(Breakthrough, on_delete=models.CASCADE)

    objects = ProjectedOutcomeQuerySet.as_manager()

    published = models.DateTimeField(default=timezone.now)

    resolved_by = models.DateField()

    confidence_level = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal(0)
    )

    name = models.CharField(max_length=255)

    description = models.TextField()

    success_criteria = models.TextField(
        help_text=_("List the criteria you’ll use to define success for this outcome"),
        null=True,
        blank=True,
    )

    # Same column as the old event_stream_id UUID, so ids keep working.
    event_stream = models.OneToOneField(
        EventStream,
        on_delete=models.RESTRICT,
        related_name="projected_outcome",
        db_column="event_stream_id",
        editable=False,
    )

    def save(self, *args, **kwargs):
        if self.event_stream_id is None:
            self.event_stream = EventStream.objects.create_for(
                self.breakthrough.user, EventStream.Type.PROJECTED_OUTCOME
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["-published"]


class ProjectedOutcomeEventMixin:
    def projected_outcome(self):
        return ProjectedOutcome.objects.get(event_stream_id=self.event_stream_id)

    def __str__(self):
        return f"ProjectedOutcome event: {self.projected_outcome().name}"


def _projected_outcome_stream_id(event):
    """The stream of the outcome a projected-outcome event is about. The FK
    is cleared when the outcome closes; the stream stays."""
    if event.projected_outcome_id is None:
        return None
    return event.projected_outcome.event_stream_id


def _get_thread_from_breakthrough(breakthrough):
    """The thread projected-outcome events are filed under: the Daily thread
    of the breakthrough's owner."""
    return Thread.objects.daily(breakthrough.user_id)


class ProjectedOutcomeMade(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(
        ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True
    )

    derived_event_stream_id = _projected_outcome_stream_id

    name = models.CharField(max_length=255)
    description = models.TextField()
    resolved_by = models.DateField()
    success_criteria = models.TextField(null=True, blank=True)

    @staticmethod
    def from_projected_outcome(projected_outcome):
        return ProjectedOutcomeMade(
            projected_outcome=projected_outcome,
            name=projected_outcome.name,
            description=projected_outcome.description,
            resolved_by=projected_outcome.resolved_by,
            success_criteria=projected_outcome.success_criteria,
            event_stream_id=projected_outcome.event_stream_id,
            thread=_get_thread_from_breakthrough(projected_outcome.breakthrough),
        )


class ProjectedOutcomeRedefined(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(
        ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True
    )

    derived_event_stream_id = _projected_outcome_stream_id

    old_name = models.CharField(max_length=255, null=True, blank=True)
    new_name = models.CharField(max_length=255, null=True, blank=True)

    old_description = models.TextField(null=True, blank=True)
    new_description = models.TextField(null=True, blank=True)

    old_success_criteria = models.TextField(null=True, blank=True)
    new_success_criteria = models.TextField(null=True, blank=True)

    @staticmethod
    def from_projected_outcome(projected_outcome, old_values):
        return ProjectedOutcomeRedefined(
            projected_outcome=projected_outcome,
            old_name=old_values.get("name"),
            new_name=projected_outcome.name,
            old_description=old_values.get("description"),
            new_description=projected_outcome.description,
            old_success_criteria=old_values.get("success_criteria"),
            new_success_criteria=projected_outcome.success_criteria,
            event_stream_id=projected_outcome.event_stream_id,
            thread=_get_thread_from_breakthrough(projected_outcome.breakthrough),
        )


class ProjectedOutcomeRescheduled(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(
        ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True
    )

    derived_event_stream_id = _projected_outcome_stream_id

    old_resolved_by = models.DateField()
    new_resolved_by = models.DateField()

    @staticmethod
    def from_projected_outcome(projected_outcome, old_resolved_by):
        return ProjectedOutcomeRescheduled(
            projected_outcome=projected_outcome,
            old_resolved_by=old_resolved_by,
            new_resolved_by=projected_outcome.resolved_by,
            event_stream_id=projected_outcome.event_stream_id,
            thread=_get_thread_from_breakthrough(projected_outcome.breakthrough),
        )


class ProjectedOutcomeClosed(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(
        ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True
    )

    derived_event_stream_id = _projected_outcome_stream_id
    breakthrough = models.ForeignKey(Breakthrough, on_delete=models.CASCADE)

    name = models.CharField(max_length=255)
    description = models.TextField()
    resolved_by = models.DateField()
    success_criteria = models.TextField(null=True, blank=True)

    @staticmethod
    def from_projected_outcome(projected_outcome):
        return ProjectedOutcomeClosed(
            projected_outcome=projected_outcome,
            breakthrough=projected_outcome.breakthrough,
            name=projected_outcome.name,
            description=projected_outcome.description,
            resolved_by=projected_outcome.resolved_by,
            success_criteria=projected_outcome.success_criteria,
            event_stream_id=projected_outcome.event_stream_id,
            thread=_get_thread_from_breakthrough(projected_outcome.breakthrough),
        )


class ProjectedOutcomeMoved(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(
        ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True
    )

    derived_event_stream_id = _projected_outcome_stream_id
    old_breakthrough = models.ForeignKey(
        Breakthrough, on_delete=models.CASCADE, related_name="moved_outcomes_from"
    )
    new_breakthrough = models.ForeignKey(
        Breakthrough, on_delete=models.CASCADE, related_name="moved_outcomes_to"
    )

    confidence_level = models.DecimalField(max_digits=5, decimal_places=2)

    name = models.CharField(max_length=255)
    description = models.TextField()
    resolved_by = models.DateField()
    success_criteria = models.TextField(null=True, blank=True)

    @staticmethod
    def from_projected_outcome(projected_outcome, old_breakthrough, new_breakthrough):
        return ProjectedOutcomeMoved(
            projected_outcome=projected_outcome,
            old_breakthrough=old_breakthrough,
            new_breakthrough=new_breakthrough,
            confidence_level=projected_outcome.confidence_level,
            name=projected_outcome.name,
            description=projected_outcome.description,
            resolved_by=projected_outcome.resolved_by,
            success_criteria=projected_outcome.success_criteria,
            event_stream_id=projected_outcome.event_stream_id,
            thread=_get_thread_from_breakthrough(old_breakthrough),
        )


class ProjectedOutcomeEvolved(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(
        ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True
    )

    derived_event_stream_id = _projected_outcome_stream_id

    note = models.CharField(max_length=512)

    @staticmethod
    def from_projected_outcome(projected_outcome, note):
        return ProjectedOutcomeEvolved(
            projected_outcome=projected_outcome,
            note=note,
            event_stream_id=projected_outcome.event_stream_id,
            thread=_get_thread_from_breakthrough(projected_outcome.breakthrough),
        )


class OtherObservationMixin:
    """Attach and detach events: the observation on the other end."""

    @cached_property
    def other_observation(self):
        """The Observation while it is open, its ObservationClosed once it is
        closed, None when neither is found."""
        observation = Observation.objects.filter(
            event_stream_id=self.other_event_stream_id
        ).first()
        if observation is not None:
            return observation

        return (
            ObservationClosed.objects.filter(event_stream_id=self.other_event_stream_id)
            .order_by("-published")
            .first()
        )


class ObservationAttached(Event, ObservationEventMixin, OtherObservationMixin):
    observation = models.ForeignKey(
        Observation, on_delete=models.SET_NULL, null=True, blank=True
    )
    # When that observation's stream is deleted (it was journalized), this
    # record of it goes too.
    other_event_stream = models.ForeignKey(
        EventStream,
        on_delete=models.CASCADE,
        related_name="+",
        db_column="other_event_stream_id",
        editable=False,
        help_text="Event stream of the observation being attached",
    )

    template = "tree/events/observation_attached.html"

    def __str__(self):
        try:
            attached_observation = Observation.objects.get(
                event_stream_id=self.other_event_stream_id
            )
            return f"Attached to: {attached_observation.situation_truncated()}"
        except Observation.DoesNotExist:
            return f"Attached observation (stream: {self.other_event_stream_id})"


class ObservationDetached(Event, ObservationEventMixin, OtherObservationMixin):
    # When that observation's stream is deleted (it was journalized), this
    # record of it goes too.
    other_event_stream = models.ForeignKey(
        EventStream,
        on_delete=models.CASCADE,
        related_name="+",
        db_column="other_event_stream_id",
        editable=False,
        help_text="Event stream of the observation being detached",
    )

    template = "tree/events/observation_detached.html"

    def __str__(self):
        try:
            detached_observation = Observation.objects.get(
                event_stream_id=self.other_event_stream_id
            )
            return f"Detached from: {detached_observation.situation_truncated()}"
        except Observation.DoesNotExist:
            return f"Detached observation (stream: {self.other_event_stream_id})"


class Statistics(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="statistics"
    )
    key = models.CharField(max_length=255)
    value = models.JSONField()
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Statistics"
        ordering = ("key",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key"], name="statistics_user_key_unique"
            ),
        ]

    def __str__(self):
        return f"{self.key}: {self.value}"


class Profile(models.Model):
    class MapProvider(models.TextChoices):
        OPENSTREETMAP = "osm", _("OpenStreetMap")
        GOOGLE_MAPS = "google", _("Google Maps")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    default_board_thread = models.ForeignKey(
        Thread, on_delete=models.SET_NULL, null=True, blank=True
    )
    habit_keywords = models.ManyToManyField(
        HabitKeyword, related_name="profiles", blank=True
    )
    # Map service used for location pins (e.g. trip POI links) in the web UI.
    map_provider = models.CharField(
        max_length=16,
        choices=MapProvider.choices,
        default=MapProvider.OPENSTREETMAP,
    )

    def __str__(self):
        return f"Profile for {self.user.username}"


class StoryQuerySet(models.QuerySet):
    def owned_by(self, user):
        return self.filter(user=user)

    def visible_to(self, user):
        """Trips ``user`` can access (theirs, or shared with them)."""
        return self.filter(event_stream__access__user=user)


class Story(models.Model):
    objects = StoryQuerySet.as_manager()

    class Type(models.TextChoices):
        TRIP = "trip", _("Trip")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stories",
    )
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.TRIP)
    title = models.CharField(max_length=255, blank=True)
    started = models.DateTimeField(default=timezone.now)
    stopped = models.DateTimeField(null=True, blank=True)

    # The trip's notes, photos and POIs, as members (they live in the user's
    # journal and habit streams too). Created with the story.
    event_stream = models.OneToOneField(
        EventStream,
        on_delete=models.RESTRICT,
        related_name="story",
        editable=False,
    )

    class Meta:
        ordering = ("-started",)
        indexes = [
            models.Index(fields=["user", "stopped", "-started"]),
        ]

    def save(self, *args, **kwargs):
        if self.event_stream_id is None:
            self.event_stream = EventStream.objects.create_for(
                self.user, EventStream.Type.TRIP
            )
        super().save(*args, **kwargs)

    def add(self, event):
        """Make ``event`` part of this trip. An event belongs to one trip at
        most; adding it to the same trip again changes nothing."""
        other = (
            event.stream_entries.filter(stream__type=EventStream.Type.TRIP)
            .exclude(stream_id=self.event_stream_id)
            .exists()
        )
        if other:
            raise ValueError(f"Event #{event.pk} is already part of another trip.")
        EventStreamEntry.objects.get_or_create(
            stream_id=self.event_stream_id, event_id=event.pk
        )

    def __str__(self):
        return self.title or f"{self.get_type_display()} #{self.pk}"


class SharedStory(models.Model):
    """Public share link for a Story. Revoke = delete the row; re-sharing
    creates a new row and therefore a fresh UUID."""

    story = models.OneToOneField(Story, on_delete=models.CASCADE, related_name="share")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Share {self.uuid} -> {self.story}"
