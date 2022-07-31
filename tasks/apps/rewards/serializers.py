from rest_framework import serializers

from .models import Claim, Claimed, DataclassJSONEncoder


class ClaimSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Claim
        fields = ['id', 'reward', 'rewarded_for']


class ClaimedSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Claimed
        fields = ['id', 'claimed', 'claimed_date']
    
    claimed = serializers.JSONField(
        encoder=DataclassJSONEncoder,
    )