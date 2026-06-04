from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from tasks.apps.rewards.models import Claim

from ..models import ChallengeStageCompleted, Element

FUNCTIONS = ("ne", "fi", "te", "si")


def function_counts(queryset):
    """Aggregate a queryset of Elements into a {ne, fi, te, si} count dict.

    Mirrors the Count(..., filter=Q(...)) idiom used for HabitTracked counts.
    """
    return queryset.aggregate(
        ne=Count("pk", filter=Q(function=Element.Function.NE)),
        fi=Count("pk", filter=Q(function=Element.Function.FI)),
        te=Count("pk", filter=Q(function=Element.Function.TE)),
        si=Count("pk", filter=Q(function=Element.Function.SI)),
    )


def tally_for_challenge(challenge):
    """The four scores counted from the moment the challenge started."""
    return function_counts(Element.objects.filter(published__gte=challenge.started_at))


def stage_target(stage):
    return {f: getattr(stage, f) for f in FUNCTIONS}


def stage_reached(stage, tally):
    """A stage is reached when the tally meets-or-exceeds every component of its
    (cumulative, absolute) target vector."""
    return all(tally[f] >= getattr(stage, f) for f in FUNCTIONS)


def granted_stage_ids(challenge):
    return set(
        ChallengeStageCompleted.objects.filter(stage__challenge=challenge).values_list(
            "stage_id", flat=True
        )
    )


@transaction.atomic
def evaluate_challenge(challenge):
    """Grant rewards for any newly satisfied stages of an active challenge.

    Idempotent: each stage is granted at most once (guarded by
    ChallengeStageCompleted). Returns the list of Claims created.
    """
    if not challenge.active:
        return []

    tally = tally_for_challenge(challenge)
    already_granted = granted_stage_ids(challenge)

    claims = []

    for stage in challenge.stages.all():
        if stage.id in already_granted:
            continue

        if not stage_reached(stage, tally):
            continue

        ChallengeStageCompleted.objects.create(stage=stage)

        claims.append(
            Claim.objects.create(
                reward=stage.reward,
                rewarded_for=f"{challenge.name}: stage {stage.order}",
            )
        )

        if stage.is_completion:
            challenge.completed_at = timezone.now()
            challenge.active = False
            challenge.save(update_fields=["completed_at", "active"])

    return claims
