from collections import namedtuple

from django.db import models

from django.utils.translation import ugettext_lazy as _
from django.utils.text import Truncator, slugify

from django.utils import timezone

from django.db.models.signals import pre_save
from django.dispatch import receiver
from polymorphic.models import PolymorphicModel

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
    # readonly-once-set
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', )

    def as_hashtag(self):
        return '#{}'.format(self.slug)
    
    @property
    def slug(self):
        return slugify(self.name)
    
    @property
    def event_stream_id(self):
        return habit_event_stream_id(self)


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
    # event_stream_id <- habit.name

    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)

    occured = models.BooleanField(default=True)

    note = models.TextField(null=True, blank=True)

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

class ObservationEventMixin:
    @property
    def observation(self):
        return Observation.objects.get(event_stream_id=self.event_stream_id)

class ObservationMade(Event, ObservationEventMixin):
    # event_stream_id <- Observation
    # thread <- Observation (can be updated)

    type = models.ForeignKey(ObservationType, on_delete=models.CASCADE)

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    interpretation = models.TextField(help_text=_("How you saw it, what you felt?"), null=True, blank=True)
    approach = models.TextField(help_text=_("How should you approach it in the future?"), null=True, blank=True)

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

class ObservationUpdated(Event):
    observation = models.ForeignKey(Observation, on_delete=models.SET_NULL, null=True)

    ### TODO add template

    comment = models.TextField(help_text=_("Update"))

    def __str__(self):
        return self.comment

class ObservationRecontextualized(Event, ObservationEventMixin):
    old_situation = models.TextField(blank=True)
    situation = models.TextField()

    ### TODO add template

    @staticmethod
    def from_observation(observation, old, published=None):
        return ObservationRecontextualized(
            published=published or timezone.now(),
            event_stream_id=observation.event_stream_id,
            thread=observation.thread,
            old_situation=old,
            situation=observation.situation,
        )

class ObservationReinterpreted(Event, ObservationEventMixin):
    old_interpretation = models.TextField(blank=True)
    interpretation = models.TextField()

    template = "tree/events/observation_reinterpreted.html"

    @staticmethod
    def from_observation(observation, old, published=None):
        return ObservationReinterpreted(
            published=published or timezone.now(),
            event_stream_id=observation.event_stream_id,
            thread=observation.thread,
            old_interpretation=old,
            interpretation=observation.interpretation,
        )

class ObservationReflectedUpon(Event, ObservationEventMixin):
    old_approach = models.TextField(blank=True)
    approach = models.TextField()

    ### TODO add template

    @staticmethod
    def from_observation(observation, old, published=None):
        return ObservationReflectedUpon(
            published=published or timezone.now(),
            event_stream_id=observation.event_stream_id,
            thread=observation.thread,
            old_approach=old,
            approach=observation.approach,
        )

class ObservationClosed(Event, ObservationEventMixin):
    type = models.ForeignKey(ObservationType, on_delete=models.CASCADE)

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    interpretation = models.TextField(help_text=_("How you saw it, what you felt?"), null=True, blank=True)
    approach = models.TextField(help_text=_("How should you approach it in the future?"), null=True, blank=True)

    ### TODO add template

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

    def __str__(self):
        return self.comment

@receiver(pre_save, sender=JournalAdded)
def update_journal_added_event_stream_id(sender, instance, *args, **kwargs):
    instance.event_stream_id = journal_added_event_stream_id(instance)


class QuickNote(models.Model):
    published = models.DateTimeField(default=timezone.now)

    note = models.TextField()