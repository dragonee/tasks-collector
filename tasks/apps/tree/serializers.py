from rest_framework import serializers

from .models import *

from functools import partial

from django.utils import timezone
from operator import itemgetter

from django.db import transaction

from rest_polymorphic.serializers import PolymorphicSerializer

class ThreadSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Thread
        fields = ['id', 'name']

class HabitSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Habit
        fields = ['id', 'name', 'description', 'slug', 'tagname']

class PlanSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Plan
        fields = ['id', 'pub_date', 'want', 'focus']

class ReflectionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Reflection
        fields = ['id', 'pub_date', 'good', 'better', 'best']

class BoardSerializer(serializers.HyperlinkedModelSerializer):
    thread = ThreadSerializer(read_only=True)

    class Meta:
        model = Board
        fields = ['id', 'date_started', 'state', 'focus', 'thread']


def spawn_observation_events(previous, current, published=None):
    if not published:
        published = timezone.now()

    def was_changed(x):
        new = getattr(current, x)
        old = getattr(previous, x)

        not_changing_null_into_empty = bool(old) or bool(new)

        return old != new and not_changing_null_into_empty
    
    def was_set(x):
        return getattr(previous, x) is None and getattr(current, x) is not None

    def filter_func(t):
        x, f = t

        return f(x)

    changed_checks = [
        ('pk', was_set),
        ('situation', was_changed), 
        ('interpretation', was_changed),
        ('approach', was_changed),
    ]

    changed_data = list(map(itemgetter(0), filter(filter_func, changed_checks)))

    if 'pk' in changed_data:
        observation_made = ObservationMade.from_observation(current, published=published)

        return [observation_made]

    events = []

    if 'situation' in changed_data:
        obj = ObservationRecontextualized.from_observation(current, previous.situation, published=published)
        events.append(obj)
    
    if 'interpretation' in changed_data:
        obj = ObservationReinterpreted.from_observation(current, previous.interpretation, published=published)
        events.append(obj)
    
    if 'approach' in changed_data:
        obj = ObservationReflectedUpon.from_observation(current, previous.approach, published=published)
        events.append(obj)
    
    return events

def get_unsaved_object(model, obj):
    if not obj:
        return model()
    
    try:
        return model.objects.get(pk=obj.pk)
    except model.DoesNotExist:
        return model()

class BaseTypeThreadSerializer(serializers.HyperlinkedModelSerializer):
    type = serializers.SlugRelatedField(
        queryset=ObservationType.objects.all(),
        slug_field='slug'
    )

    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(),
        slug_field='name'
    )

class ObservationSerializer(BaseTypeThreadSerializer):

    class Meta:
        model = Observation
        fields = ['id', 'pub_date', 'thread', 'type', 'situation', 'interpretation', 'approach']
    
    @transaction.atomic
    def save(self, *args, **kwargs):
        old_obj = get_unsaved_object(Observation, self.instance)
        new_obj = super().save(*args, **kwargs)

        events = spawn_observation_events(
            old_obj,
            new_obj,
            published=timezone.now()
        )

        for event in events:
            event.save()
        
        return new_obj


class ObservationUpdatedSerializer(serializers.ModelSerializer):
    observation_fields = ObservationSerializer(read_only=True)

    class Meta:
        model = ObservationUpdated
        fields = [ 'id', 'comment', 'published', 'observation_fields', 'observation' ]

class MultipleObservationUpdatedSerializer(serializers.ModelSerializer):

    class Meta:
        model = ObservationUpdated
        fields = [ 'id', 'comment', 'published', 'event_stream_id' ]

class ObservationWithUpdatesSerializer(ObservationSerializer):
    updates = MultipleObservationUpdatedSerializer(
        many=True, 
        read_only=True, 
        source='observationupdated_set'
    )

    class Meta(ObservationSerializer.Meta):
        fields = ObservationSerializer.Meta.fields + ['updates']

class JournalAddedSerializer(serializers.ModelSerializer):
    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(),
        slug_field='name'
    )

    class Meta:
        model = JournalAdded
        fields = [ 'id', 'comment', 'published', 'thread', ]

class QuickNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuickNote
        fields = [ 'id', 'published', 'note']


class ObservationMadeSerializer(BaseTypeThreadSerializer):
    class Meta:
        model = ObservationMade
        fields = [
            'id',
            'published',
            'event_stream_id',
            'thread',
            'type',
            'situation',
            'interpretation',
            'approach'
        ]

class ObservationRecontextualizedSerializer(BaseTypeThreadSerializer):
    class Meta:
        model = ObservationRecontextualized
        fields = [
            'id',
            'published',
            'event_stream_id',
            'thread',
            'situation',
            'old_situation'
        ]

class ObservationReinterpretedSerializer(BaseTypeThreadSerializer):
    class Meta:
        model = ObservationReinterpreted
        fields = [
            'id',
            'published',
            'event_stream_id',
            'thread',
            'interpretation',
            'old_interpretation'
        ]

class ObservationReflectedUponSerializer(BaseTypeThreadSerializer):
    class Meta:
        model = ObservationReflectedUpon
        fields = [
            'id',
            'published',
            'event_stream_id',
            'thread',
            'approach',
            'old_approach'
        ]

class ObservationClosedSerializer(BaseTypeThreadSerializer):
    class Meta:
        model = ObservationClosed
        fields = [
            'id',
            'published',
            'event_stream_id',
            'thread',
            'type',
            'situation',
            'interpretation',
            'approach'
        ]

class ObservationEventSerializer(PolymorphicSerializer):
    model_serializer_mapping = {
        ObservationMade: ObservationMadeSerializer,
        ObservationRecontextualized: ObservationRecontextualizedSerializer,
        ObservationReinterpreted: ObservationReinterpretedSerializer,
        ObservationReflectedUpon: ObservationReflectedUponSerializer,
        ObservationClosed: ObservationClosedSerializer,
        ObservationUpdated: MultipleObservationUpdatedSerializer,
    }


class tree_iterator:
    """Preorder traversal tree iterator"""

    def __init__(self, tree, key='children'):
        self.key = key

        # Internally this iterator requires top-level list,
        # so if given a valid node (that has children key)
        # wrap it in a list
        if key in tree:
            tree = [tree]

        self.iterators = [
            iter(tree)
        ]

    def __iter__(self):
        return self

    def _find_next_path(self):
        try:
            value = next(self.iterators[-1])
        except StopIteration:
            # If there are no leaves to process
            # remove last iterator and rerun the process.
            # This is how it traverses upwards.
            #
            # Recursion handles for us multi-level jumps.
            #
            # Last pop is handled in __next__()
            self.iterators.pop()
            return self._find_next_path()

        # Before returning a value,
        # setup iterator-path to a node's children for future
        # iterations. That's how it traverses deeper.
        if self.key in value and len(value[self.key]) > 0:
            self.iterators.append(iter(value[self.key]))

        return value

    def __next__(self):
        try:
            return self._find_next_path()
        except IndexError:
            # We have popped out of self.iterators to use
            raise StopIteration

def _state(key, default, item):
    return item.get('state', {}).get(key, default)

def state(key, default=None):
    return partial(_state, key, default)

def _marker(key, default, item):
    return item.get('data', {}).get('meaningfulMarkers', {}).get(key, default)

def marker(key, default=None):
    return partial(_marker, key, default)

def ilen(iter):
    return sum(1 for _ in iter)

class BoardSummary(object):
    def __init__(self, board):
        self.board = board

    def filter_tree(self, pred):
        return filter(pred, tree_iterator(self.board.before))

    def finished(self):
        return self.filter_tree(state('checked'))

    def postponed(self):
        return self.filter_tree(marker('postponedFor'))

    def finished_count(self):
        return ilen(self.finished())

    def postponed_count(self):
        return ilen(self.postponed())

    def task_count(self):
        return ilen(tree_iterator(self.board.before))

    def days(self):
        return (self.board.published - self.board.date_started).days

    def observations(self):
        # XXX TODO optimize N-question problem

        # XXX TODO hack
        if self.board.thread.name != 'Daily':
            return []

        return Observation.objects.filter(pub_date__range=(
            self.board.date_started, 
            self.board.published
        ))