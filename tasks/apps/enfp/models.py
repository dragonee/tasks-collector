from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Element(models.Model):
    """A single thing you did, tagged with the cognitive function it exercised.

    Append-only: rows are never updated. The four function scores are *derived*
    by aggregation (see services.evaluation), mirroring how HabitTracked counts
    are derived rather than stored as mutable counters.
    """

    class Function(models.TextChoices):
        NE = "Ne", _("Extraverted Intuition (Ne)")
        FI = "Fi", _("Introverted Feeling (Fi)")
        TE = "Te", _("Extraverted Thinking (Te)")
        SI = "Si", _("Introverted Sensing (Si)")

    function = models.CharField(max_length=2, choices=Function.choices)
    description = models.TextField(blank=True)
    published = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-published",)
        indexes = [
            models.Index(fields=["function", "published"]),
        ]

    def __str__(self):
        return f"{self.get_function_display()} @ {self.published:%Y-%m-%d}"


class Challenge(models.Model):
    """A configurable, multi-stage progression that grants rewards as the four
    function scores (counted since ``started_at``) reach successive targets."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    # Counts for this challenge are measured from this moment onward.
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-started_at",)

    def __str__(self):
        return self.name


class ChallengeStage(models.Model):
    """One rung of a Challenge: a cumulative target vector (ne, fi, te, si) that,
    once met-or-exceeded, grants ``reward``."""

    challenge = models.ForeignKey(
        Challenge, related_name="stages", on_delete=models.CASCADE
    )
    order = models.PositiveSmallIntegerField(default=0)

    ne = models.PositiveSmallIntegerField(default=0)
    fi = models.PositiveSmallIntegerField(default=0)
    te = models.PositiveSmallIntegerField(default=0)
    si = models.PositiveSmallIntegerField(default=0)

    # String ref keeps app-load order robust across the rewards <-> enfp boundary.
    reward = models.ForeignKey("rewards.Reward", on_delete=models.PROTECT)
    is_completion = models.BooleanField(default=False)

    class Meta:
        ordering = ("order",)

    def __str__(self):
        return f"{self.challenge.name} #{self.order} ({self.ne},{self.fi},{self.te},{self.si})"


class ChallengeStageCompleted(models.Model):
    """Append-only record that a stage's reward was granted. Its existence is the
    idempotency guard that prevents a stage from being granted twice."""

    stage = models.ForeignKey(ChallengeStage, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-completed_at",)

    def __str__(self):
        return str(self.stage)
