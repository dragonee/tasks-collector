from rest_framework import serializers

from .models import Claim, Claimed, ClaimedReward

import dataclasses

class CRField(serializers.Field):
    def to_representation(self, value):
        return [dataclasses.asdict(a) for a in value]

    def to_internal_value(self, data):
        return [ClaimedReward(**a) for a in data]


class ClaimSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Claim
        fields = ['id', 'reward', 'rewarded_for']


class ClaimedSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Claimed
        fields = ['id', 'claimed', 'claimed_date']
    
    claimed = CRField()