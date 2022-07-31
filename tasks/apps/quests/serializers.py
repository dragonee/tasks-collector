from rest_framework import serializers

from .models import Quest, QuestJournal


class QuestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Quest
        fields = ['name', 'slug', 'stage', 'date_closed']
    
    slug = serializers.SlugField(max_length=255)


class QuestJournalSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = QuestJournal
        fields = ['id', 'quest',  'stage', 'text']
    
    quest = QuestSerializer()

    def create(self, validated_data):
        quest_data = validated_data['quest']

        try: 
            quest_obj = Quest.objects.get(slug=quest_data['slug'])
        except Quest.DoesNotExist:
            quest_obj = Quest(**quest_data)

        journal_stage_value = self.validated_data.get('stage', 0)

        if quest_obj.stage < journal_stage_value:
            quest_obj.stage = journal_stage_value
        
        quest_obj.save()

        quest_journal_data = {k:v for k,v in validated_data.items() if k != 'quest'}

        return QuestJournal.objects.create(
            **quest_journal_data,
            quest=quest_obj,
        )
    


