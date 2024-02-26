from django.db import models

from django.utils.translation import ugettext_lazy as _
from django.utils.text import Truncator

from django.utils import timezone

from django.db.models.signals import post_save
from django.dispatch import receiver

def empty_dict():
    return {}

def default_state():
    return []

class Thread(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', )


class Event(models.Model):
    published = models.DateTimeField(default=timezone.now)

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)


class BoardCommitted(Event):
    focus = models.CharField(max_length=255)

    before = models.JSONField(default=default_state)
    after = models.JSONField(default=default_state)

    transitions = models.JSONField(default=empty_dict)

    date_started = models.DateTimeField(default=timezone.now)

    @property
    def date_closed(self):
        return self.published


class Habit(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name', )


class HabitTracked(Event):
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)

    occured = models.BooleanField(default=True)

    note = models.TextField(null=True, blank=True)

    def __str__(self):
        return "{} {}".format(self.habit, self.published)


class EditableHabitsLine(models.Model):
    pub_date = models.DateField()

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE)

    line = models.TextField(blank=True)

    def __str__(self):
        return "{}: {}".format(self.pub_date, self.line)
    
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

    situation = models.TextField(help_text=_("What happened?"), null=True, blank=True)
    interpretation = models.TextField(help_text=_("How you saw it, what you felt?"), null=True, blank=True)
    approach = models.TextField(help_text=_("How should you approach it in the future?"), null=True, blank=True)

    date_closed = models.DateField(help_text=_("Closed"), null=True, blank=True)

    class Meta:
        ordering = ('-pub_date', )

    def __str__(self):
        return "{}: {} ({})".format(
            self.pub_date,
            Truncator(self.situation).words(6),
            self.thread
        )


class Update(models.Model):
    pub_date = models.DateField(auto_now_add=True)

    observation = models.ForeignKey(Observation, on_delete=models.CASCADE)

    comment = models.TextField(help_text=_("Update"))

    def __str__(self):
        return self.comment
