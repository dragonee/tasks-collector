from rest_framework import serializers

from .models import Quest, QuestJournal


class SimpleQuestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Quest
        fields = ['name', 'slug', 'stage', 'date_closed', 'url']
    
    slug = serializers.SlugField(max_length=255)

    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        return obj.get_absolute_url()

class SimpleQuestJournalSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = QuestJournal
        fields = ['stage', 'text']


class QuestSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Quest
        fields = ['name', 'slug', 'stage', 'date_closed', 'journal']
    
    slug = serializers.SlugField(max_length=255)    
    journal = serializers.SerializerMethodField()

    def get_journal(self, obj):
        items = obj.questjournal_set.all().order_by('id')
        return SimpleQuestJournalSerializer(items, many=True).data


class QuestJournalSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = QuestJournal
        fields = ['id', 'quest',  'stage', 'text']
    
    quest = SimpleQuestSerializer()

    def create(self, validated_data):
        quest_data = validated_data['quest']

        try: 
            quest_obj = Quest.objects.get(slug=quest_data['slug'])
        except Quest.DoesNotExist:
            quest_obj = Quest(
                name=quest_data['name'],
                slug=quest_data['slug']
            )

        journal_stage_value = self.validated_data.get('stage', 0)

        if quest_obj.stage < journal_stage_value:
            quest_obj.stage = journal_stage_value
        
        if quest_data.get('date_closed') and not quest_obj.date_closed:
            quest_obj.date_closed = quest_data['date_closed']

        quest_obj.save()

        quest_journal_data = {k:v for k,v in validated_data.items() if k != 'quest'}

        return QuestJournal.objects.create(
            **quest_journal_data,
            quest=quest_obj,
        )
    


