from collections import namedtuple

from django.db import models

from django.utils.translation import gettext_lazy as _
from django.utils.text import Truncator, slugify

from django.utils import timezone

from django.db.models.signals import pre_save
from django.dispatch import receiver
from polymorphic.models import PolymorphicModel

from decimal import Decimal
import uuid

from .uuid_generators import board_event_stream_id, habit_event_stream_id, journal_added_event_stream_id, board_event_stream_id_from_thread

from .utils.datetime import aware_from_date

def empty_dict():
    return {}

def default_state():
    return []

class Thread(models.Model):
    # readonly-once-set
    # if you need to change name, a migration needs to be run
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', )


class Event(PolymorphicModel):
    published = models.DateTimeField(default=timezone.now)

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)

    event_stream_id = models.UUIDField(editable=False)

    class Meta:
        indexes = [
            models.Index(fields=['published']),
            models.Index(fields=['event_stream_id', 'published'])
        ]

        ordering = (
            'published',
        )

    def __str__(self):
        return "[{cls}] #{pk}".format(
            cls=self.get_real_instance_class().__name__, 
            pk=self.pk
        )


class BoardCommitted(Event):
    # thread set manually from board
    # event_stream_id <- thread

    focus = models.CharField(max_length=255)

    before = models.JSONField(default=default_state)
    after = models.JSONField(default=default_state)

    transitions = models.JSONField(default=empty_dict)

    date_started = models.DateTimeField(default=timezone.now)

    @property
    def date_closed(self):
        return self.published

@receiver(pre_save, sender=BoardCommitted)
def update_board_committed_event_stream_id(sender, instance, *args, **kwargs):
    instance.event_stream_id = board_event_stream_id_from_thread(instance.thread)


class Habit(models.Model):
    # Display name
    name = models.CharField(max_length=255)
    
    # URL Slug
    slug = models.SlugField(max_length=255, unique=True)

    # hashtag for matching
    tagname = models.SlugField(max_length=255, unique=True, allow_unicode=True)

    event_stream_id = models.UUIDField(default=uuid.uuid4, editable=False)

    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', )

    def as_hashtag(self):
        return '#{}'.format(self.tagname)


Diff = namedtuple('Diff', ['old', 'new'])

def field_has_changed(instance, field):
    model = type(instance)

    new_value = getattr(instance, field)

    try:
        old = model.objects.get(pk=instance.pk)

        old_value = getattr(old, field)

        if getattr(old, field) == getattr(instance, field):
            return False
        
        return Diff(old=old_value, new=new_value)
    except model.DoesNotExist:
        return Diff(old=None, new=new_value)


@receiver(pre_save, sender=Habit)
def on_habit_name_change_update_event_stream_id(sender, instance, *args, **kwargs):
    changed = field_has_changed(instance, 'event_stream_id')

    if not changed or not changed.old:
        return
    
    Event.objects.filter(
        event_stream_id=changed.old
    ).update(
        event_stream_id=changed.new
    )

class HabitTracked(Event):
    # thread must be set manually
    # event_stream_id <- habit.event_stream_id (v2)

    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)

    occured = models.BooleanField(default=True)

    note = models.TextField(null=True, blank=True)

    template = "tree/events/habit_tracked.html"

    def __str__(self):
        return "{} {}".format(self.habit, self.published)

@receiver(pre_save, sender=HabitTracked)
def update_habit_tracked_event_stream_id(sender, instance, *args, **kwargs):
    instance.event_stream_id = habit_event_stream_id(instance)

    
class Board(models.Model):
    date_started = models.DateTimeField(default=timezone.now)

    state = models.JSONField(default=default_state, blank=True)

    focus = models.CharField(max_length=255, null=True, blank=True)

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, null=True)
    class Meta:
        ordering = ('-date_started',)

    def __str__(self):
        if not self.focus:
            return str(self.thread)

        return "{} {}".format(self.focus, self.thread)
    
    @property
    def event_stream_id(self):
        return board_event_stream_id(self)


class Reflection(models.Model):
    pub_date = models.DateField()

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)

    good = models.TextField(help_text=_("What did you do well today?"), null=True, blank=True)
    better = models.TextField(help_text=_("How could you improve? What could you do better?"), null=True, blank=True)
    best = models.TextField(help_text=_("What do you need to do if you want to be the best version of yourself?"), null=True, blank=True)

    class Meta:
        ordering = ('-pub_date', )

    def __str__(self):
        return "{} ({})".format(self.pub_date, self.thread)


class Plan(models.Model):
    pub_date = models.DateField()

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)

    focus = models.TextField(help_text=_("What is your primary focus?"), null=True, blank=True)
    want = models.TextField(help_text=_("What feelings/thoughts/desires are currently on your mind?"), null=True, blank=True)

    class Meta:
        ordering = ('-pub_date', )

    def __str__(self):
        return "{} ({})".format(self.pub_date, self.thread)

class ObservationType(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)

    def __str__(self):
        return self.name


class Observation(models.Model):
    pub_date = models.DateField()

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)
    type = models.ForeignKey(ObservationType, on_delete=models.CASCADE)

    event_stream_id = models.UUIDField(default=uuid.uuid4, editable=False)

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    interpretation = models.TextField(help_text=_("How you saw it, what you felt?"), null=True, blank=True)
    approach = models.TextField(help_text=_("How should you approach it in the future?"), null=True, blank=True)

    class Meta:
        ordering = ('-pub_date', '-pk')

    def __str__(self):
        return "{}: {} ({})".format(
            self.pub_date,
            Truncator(self.situation).words(6),
            self.thread
        )
    
    def copy(self, as_new=True):
        kwargs = {}

        if not as_new:
            kwargs['pk'] = self.pk
            kwargs['event_stream_id'] = self.event_stream_id

        return Observation(
            pub_date=self.pub_date,
            thread_id=self.thread_id,
            type_id=self.type_id,

            situation=self.situation,
            interpretation=self.interpretation,
            approach=self.approach,

            **kwargs
        )

def coalesce(value, default=''):
    return value if value is not None else default

class ObservationPropertyEventMixin:
    @property
    def observation(self):
        return Observation.objects.get(event_stream_id=self.event_stream_id)

class ObservationEventMixin:
    def situation(self):
        ### XXX Situation at the time of the event or current?
        ### For now, current is implemented here
        event = Event.objects.instance_of(
            ObservationMade,
            ObservationRecontextualized
        ).filter(
            event_stream_id=self.event_stream_id
        ).order_by(
            '-published'
        ).first()

        if not event:
            raise Observation.DoesNotExist
        
        return event.situation

class ObservationMade(Event, ObservationEventMixin, ObservationPropertyEventMixin):
    # event_stream_id <- Observation
    # thread <- Observation (can be updated)

    type = models.ForeignKey(ObservationType, on_delete=models.CASCADE)

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    interpretation = models.TextField(help_text=_("How you saw it, what you felt?"), null=True, blank=True)
    approach = models.TextField(help_text=_("How should you approach it in the future?"), null=True, blank=True)

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
            self.published,
            Truncator(self.situation).words(6),
            self.thread
        )

class ObservationUpdated(Event, ObservationEventMixin):
    observation = models.ForeignKey(Observation, on_delete=models.SET_NULL, null=True, blank=True)

    template = "tree/events/observation_updated.html"

    comment = models.TextField(help_text=_("Update"))

    def __str__(self):
        return self.comment

class ObservationRecontextualized(Event, ObservationEventMixin, ObservationPropertyEventMixin):
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

class ObservationReinterpreted(Event, ObservationEventMixin, ObservationPropertyEventMixin):
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

class ObservationReflectedUpon(Event, ObservationEventMixin, ObservationPropertyEventMixin):
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
    interpretation = models.TextField(help_text=_("How you saw it, what you felt?"), null=True, blank=True)
    approach = models.TextField(help_text=_("How should you approach it in the future?"), null=True, blank=True)

    template = "tree/events/observation_closed.html"

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

observation_event_types = (
    ObservationMade,
    ObservationClosed,
    ObservationRecontextualized,
    ObservationReflectedUpon,
    ObservationReinterpreted,
    ObservationUpdated,
)

@receiver(pre_save)
def copy_observation_to_update_events(sender, instance, *args, **kwargs):
    if not isinstance(instance, observation_event_types):
        return

    if not instance.thread_id and instance.observation:
        instance.thread_id = instance.observation.thread_id

    instance.event_stream_id = instance.observation.event_stream_id


@receiver(pre_save, sender=Observation)
def on_observation_thread_change_update_events(sender, instance, *args, **kwargs):
    changed = field_has_changed(instance, 'thread_id')

    if not changed or not changed.old:
        return

    if instance.event_stream_id is None:
        return

    Event.objects.filter(
        event_stream_id=instance.event_stream_id
    ).update(
        thread=instance.thread
    )

class JournalAdded(Event):
    comment = models.TextField(help_text=_("Update"))

    template = "tree/events/journal_added.html"

    def __str__(self):
        return self.comment

@receiver(pre_save, sender=JournalAdded)
def update_journal_added_event_stream_id(sender, instance, *args, **kwargs):
    instance.event_stream_id = journal_added_event_stream_id(instance)


class QuickNote(models.Model):
    published = models.DateTimeField(default=timezone.now)

    note = models.TextField()

REFLECTION_LINE_PREFIXES = (
    ('[x] ', 'good'),
    ('[~] ', 'better'),
    ('[^] ', 'best'),
)

def extract_reflection_lines(note):
    lines = note.split('\n')

    return [
        (field, line.replace(prefix, '', 1))
        for line in lines
        for prefix, field in REFLECTION_LINE_PREFIXES
        if prefix in line[:12]
    ]


def append_lines_to_value(value, lines):
    if not value:
        return '\n'.join(lines)
    
    if not lines:
        return value

    return (value + '\n' + '\n'.join(lines)).strip()


def add_reflection_items(journal_added):
    pub_date = journal_added.published.date()

    reflection_lines = extract_reflection_lines(journal_added.comment)

    if not reflection_lines:
        return

    try:
        reflection = Reflection.objects.get(
            pub_date=pub_date,
            thread=journal_added.thread
        )
    except Reflection.DoesNotExist:
        reflection = Reflection(
            pub_date=pub_date,
            thread=journal_added.thread
        )

    for field_name in ('good', 'better', 'best'):
        items = (line for field, line in reflection_lines if field == field_name)

        new_value = append_lines_to_value(
            getattr(reflection, field_name), 
            items
        )

        setattr(reflection, field_name, new_value)

    reflection.save()


def save_or_remove_object_if_empty(object, fields):
    is_empty = not any(getattr(object, field) for field in fields)

    if not is_empty:
        object.save()
    elif object.pk:
        object.delete()


class JournalTag(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    journals = models.ManyToManyField(JournalAdded, related_name='tags', blank=True)

    def __str__(self):
        return self.name

class Breakthrough(models.Model):
    slug = models.SlugField(max_length=255, unique=True)

    published = models.DateTimeField(default=timezone.now)
    last_updated = models.DateTimeField(auto_now=True)

    areas_of_concern = models.TextField(_('Areas of concern'), help_text=_("List areas of life thet give you most discomfort"))

    theme = models.CharField(_('Theme of the year'), max_length=255, help_text=_("A phrase that captures your year"))


class ProjectedOutcome(models.Model):
    breakthrough = models.ForeignKey(Breakthrough, on_delete=models.CASCADE)

    published = models.DateTimeField(default=timezone.now)

    resolved_by = models.DateField()

    confidence_level = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal(0))

    name = models.CharField(max_length=255)

    description = models.TextField()

    success_criteria = models.TextField(
        help_text=_("List the criteria you’ll use to define success for this outcome"),
        null=True,
        blank=True
    )

### XXX TODO -> evolution of projected outcomes