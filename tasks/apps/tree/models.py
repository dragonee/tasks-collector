from django.db import models
from django.contrib.postgres.fields import JSONField

def default_state():
    return []

class Thread(models.Model):
    name = models.CharField(max_length=255)

class Board(models.Model):
    date_started = models.DateTimeField(auto_now_add=True)

    date_closed = models.DateTimeField(null=True, blank=True)

    state = JSONField(default=default_state, blank=True)

    focus = models.CharField(max_length=255, null=True, blank=True)

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, null=True)

    class Meta:
        ordering = ('-date_started',)

    def __str__(self):
        if not self.focus:
            return self.date_started

        return "{} {}".format(self.focus, self.date_started)


class Reflection(models.Model):
    pub_date = models.DateField()

    good = models.TextField(null=True, blank=True)
    better = models.TextField(null=True, blank=True)
    best = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ('-pub_date', )

    def __str__(self):
        return "{}".format(self.pub_date)


class Plan(models.Model):
    pub_date = models.DateField()

    focus = models.TextField(null=True, blank=True)
    want = models.TextField(null=True, blank=True)
    in_sync = models.BooleanField(default=False)

    class Meta:
        ordering = ('-pub_date', )

    def __str__(self):
        return "{}".format(self.pub_date)
