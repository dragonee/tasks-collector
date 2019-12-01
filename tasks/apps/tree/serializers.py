from rest_framework import serializers

from .models import Board


class BoardSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Board
        fields = ['id', 'date_started', 'date_closed', 'state', 'focus']