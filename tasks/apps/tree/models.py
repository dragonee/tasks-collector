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
