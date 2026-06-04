from django.db import transaction

from rest_framework import serializers

from .models import Challenge, Element
from .services.evaluation import (
    evaluate_challenge,
    granted_stage_ids,
    stage_reached,
    stage_target,
    tally_for_challenge,
)


class ElementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Element
        fields = ["id", "function", "description", "published"]

    @transaction.atomic
    def save(self, *args, **kwargs):
        # Logging an element may push one or more active challenges past a stage
        # threshold. Re-evaluate them in the same transaction as the write,
        # mirroring how ObservationSerializer.save() emits change events.
        element = super().save(*args, **kwargs)

        for challenge in Challenge.objects.filter(active=True):
            evaluate_challenge(challenge)

        return element


class ChallengeSerializer(serializers.ModelSerializer):
    """Read-only challenge view that also computes, per active challenge, the
    current tally and each stage's reached/claimed state plus the next unmet
    stage. Tally/grant lookups are cached per instance to avoid duplicate queries."""

    current = serializers.SerializerMethodField()
    stages = serializers.SerializerMethodField()
    next_stage = serializers.SerializerMethodField()

    class Meta:
        model = Challenge
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "started_at",
            "completed_at",
            "active",
            "current",
            "stages",
            "next_stage",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tally_cache = {}
        self._granted_cache = {}

    def _tally(self, challenge):
        if challenge.id not in self._tally_cache:
            self._tally_cache[challenge.id] = tally_for_challenge(challenge)
        return self._tally_cache[challenge.id]

    def _granted(self, challenge):
        if challenge.id not in self._granted_cache:
            self._granted_cache[challenge.id] = granted_stage_ids(challenge)
        return self._granted_cache[challenge.id]

    def _stage_dict(self, stage):
        return {
            "id": stage.id,
            "order": stage.order,
            "target": stage_target(stage),
            "reward": stage.reward.slug,
            "reward_name": stage.reward.name,
            "reward_emoji": stage.reward.emoji,
            "is_completion": stage.is_completion,
        }

    def get_current(self, challenge):
        return self._tally(challenge)

    def get_stages(self, challenge):
        tally = self._tally(challenge)
        granted = self._granted(challenge)

        out = []
        for stage in challenge.stages.all():
            data = self._stage_dict(stage)
            data["reached"] = stage_reached(stage, tally)
            data["claimed"] = stage.id in granted
            out.append(data)
        return out

    def get_next_stage(self, challenge):
        granted = self._granted(challenge)
        for stage in challenge.stages.all():
            if stage.id not in granted:
                return self._stage_dict(stage)
        return None
