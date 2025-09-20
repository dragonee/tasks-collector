from collections import namedtuple

from django.db import models

from django.utils.translation import gettext_lazy as _
from django.utils.text import Truncator, slugify

from django.utils import timezone

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from polymorphic.models import PolymorphicModel

from calendar import monthrange

from datetime import timedelta

from django.urls import reverse

from decimal import Decimal
import uuid

from django.conf import settings

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

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
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
            user_id=self.user_id,

            situation=self.situation,
            interpretation=self.interpretation,
            approach=self.approach,

            **kwargs
        )

    def situation_truncated(self):
        return Truncator(self.situation).words(6)

    def get_absolute_url(self):
        return reverse('public-observation-edit', kwargs={'observation_id': self.pk})

def coalesce(value, default=''):
    return value if value is not None else default

class ObservationPropertyEventMixin:
    @property
    def observation(self):
        return Observation.objects.get(event_stream_id=self.event_stream_id)

class ObservationEventMixin:
    def url(self):
        try:
            observation = Observation.objects.get(event_stream_id=self.event_stream_id)
            return observation.get_absolute_url()
        except Observation.DoesNotExist:
            return reverse('public-observation-closed-detail', kwargs={'event_stream_id': self.event_stream_id})

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

    def situation_at_creation(self):
        event = Event.objects.instance_of(
            ObservationMade,
            ObservationRecontextualized
        ).filter(
            event_stream_id=self.event_stream_id,
            published__lte=self.published
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

    # This allows us to contribute to one weekly/monthly reflection
    if journal_added.thread.name == 'Weekly':
        pub_date = pub_date + timedelta(days=(6 - pub_date.weekday()))
    
    if journal_added.thread.name == 'big-picture':
        pub_date = pub_date.replace(day=monthrange(pub_date.year, pub_date.month)[1])

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

    event_stream_id = models.UUIDField(default=uuid.uuid4, editable=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-published']


class ProjectedOutcomeEventMixin:
    def projected_outcome(self):
        return ProjectedOutcome.objects.get(event_stream_id=self.event_stream_id)

    def __str__(self):
        return f"ProjectedOutcome event: {self.projected_outcome().name}"


class ProjectedOutcomeMade(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True)
    
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
            thread=projected_outcome.breakthrough.thread if hasattr(projected_outcome.breakthrough, 'thread') else Thread.objects.get(name='Daily')
        )


class ProjectedOutcomeRedefined(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True)
    
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
            old_name=old_values.get('name'),
            new_name=projected_outcome.name,
            old_description=old_values.get('description'),
            new_description=projected_outcome.description,
            old_success_criteria=old_values.get('success_criteria'),
            new_success_criteria=projected_outcome.success_criteria,
            event_stream_id=projected_outcome.event_stream_id,
            thread=projected_outcome.breakthrough.thread if hasattr(projected_outcome.breakthrough, 'thread') else Thread.objects.get(name='Daily')
        )


class ProjectedOutcomeRescheduled(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True)
    
    old_resolved_by = models.DateField()
    new_resolved_by = models.DateField()

    @staticmethod
    def from_projected_outcome(projected_outcome, old_resolved_by):
        return ProjectedOutcomeRescheduled(
            projected_outcome=projected_outcome,
            old_resolved_by=old_resolved_by,
            new_resolved_by=projected_outcome.resolved_by,
            event_stream_id=projected_outcome.event_stream_id,
            thread=projected_outcome.breakthrough.thread if hasattr(projected_outcome.breakthrough, 'thread') else Thread.objects.get(name='Daily')
        )


class ProjectedOutcomeClosed(Event, ProjectedOutcomeEventMixin):
    projected_outcome = models.ForeignKey(ProjectedOutcome, on_delete=models.SET_NULL, null=True, blank=True)
    
    name = models.CharField(max_length=255)
    description = models.TextField()
    resolved_by = models.DateField()
    success_criteria = models.TextField(null=True, blank=True)

    @staticmethod
    def from_projected_outcome(projected_outcome):
        return ProjectedOutcomeClosed(
            projected_outcome=projected_outcome,
            name=projected_outcome.name,
            description=projected_outcome.description,
            resolved_by=projected_outcome.resolved_by,
            success_criteria=projected_outcome.success_criteria,
            event_stream_id=projected_outcome.event_stream_id,
            thread=projected_outcome.breakthrough.thread if hasattr(projected_outcome.breakthrough, 'thread') else Thread.objects.get(name='Daily')
        )


def normalize_for_comparison(value):
    """Normalize None and empty strings to empty string for comparison"""
    return coalesce(value, '')


# Signal handlers for ProjectedOutcome event sourcing
@receiver(post_save, sender=ProjectedOutcome)
def create_initial_projected_outcome_made_event(sender, instance, created, **kwargs):
    if created:
        event = ProjectedOutcomeMade.from_projected_outcome(instance)
        event.save()


@receiver(pre_save, sender=ProjectedOutcome)
def create_projected_outcome_events(sender, instance, **kwargs):
    if instance.pk is None:
        return
    
    try:
        old_instance = ProjectedOutcome.objects.get(pk=instance.pk)
    except ProjectedOutcome.DoesNotExist:
        return
    
    # Check for redefined fields (name, description, success_criteria)
    redefined_fields = {}
    if normalize_for_comparison(old_instance.name) != normalize_for_comparison(instance.name):
        redefined_fields['name'] = old_instance.name
    if normalize_for_comparison(old_instance.description) != normalize_for_comparison(instance.description):
        redefined_fields['description'] = old_instance.description
    if normalize_for_comparison(old_instance.success_criteria) != normalize_for_comparison(instance.success_criteria):
        redefined_fields['success_criteria'] = old_instance.success_criteria
    
    if redefined_fields:
        event = ProjectedOutcomeRedefined.from_projected_outcome(instance, redefined_fields)
        event.save()
    
    # Check for rescheduled
    if old_instance.resolved_by != instance.resolved_by:
        event = ProjectedOutcomeRescheduled.from_projected_outcome(instance, old_instance.resolved_by)
        event.save()


@receiver(pre_save, sender=ProjectedOutcomeMade)
def update_projected_outcome_made_event_stream_id(sender, instance, **kwargs):
    if instance.projected_outcome:
        instance.event_stream_id = instance.projected_outcome.event_stream_id


@receiver(pre_save, sender=ProjectedOutcomeRedefined)
def update_projected_outcome_redefined_event_stream_id(sender, instance, **kwargs):
    if instance.projected_outcome:
        instance.event_stream_id = instance.projected_outcome.event_stream_id


@receiver(pre_save, sender=ProjectedOutcomeRescheduled)
def update_projected_outcome_rescheduled_event_stream_id(sender, instance, **kwargs):
    if instance.projected_outcome:
        instance.event_stream_id = instance.projected_outcome.event_stream_id


@receiver(pre_save, sender=ProjectedOutcomeClosed)
def update_projected_outcome_closed_event_stream_id(sender, instance, **kwargs):
    if instance.projected_outcome:
        instance.event_stream_id = instance.projected_outcome.event_stream_id



class ObservationAttached(Event, ObservationEventMixin):
    observation = models.ForeignKey(Observation, on_delete=models.SET_NULL, null=True, blank=True)
    other_event_stream_id = models.UUIDField(help_text="Event stream ID of the observation being attached")
    
    template = "tree/events/observation_attached.html"

    def __str__(self):
        try:
            attached_observation = Observation.objects.get(event_stream_id=self.other_event_stream_id)
            return f"Attached to: {attached_observation.situation_truncated()}"
        except Observation.DoesNotExist:
            return f"Attached observation (stream: {self.other_event_stream_id})"


class ObservationDetached(Event, ObservationEventMixin):
    other_event_stream_id = models.UUIDField(help_text="Event stream ID of the observation being detached")
    
    template = "tree/events/observation_detached.html"

    def __str__(self):
        try:
            detached_observation = Observation.objects.get(event_stream_id=self.other_event_stream_id)
            return f"Detached from: {detached_observation.situation_truncated()}"
        except Observation.DoesNotExist:
            return f"Detached observation (stream: {self.other_event_stream_id})"

class Statistics(models.Model):
    key = models.CharField(max_length=255, unique=True)
    value = models.JSONField()
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Statistics"
        ordering = ('key',)
    
    def __str__(self):
        return f"{self.key}: {self.value}"

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    default_board_thread = models.ForeignKey(Thread, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"Profile for {self.user.username}"