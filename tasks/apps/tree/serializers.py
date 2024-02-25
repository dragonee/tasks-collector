from rest_framework import serializers

from .models import Board, Thread, Plan, Reflection, Observation, ObservationType

from functools import partial

class ThreadSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Thread
        fields = ['id', 'name']

class PlanSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Plan
        fields = ['id', 'pub_date', 'want', 'focus', 'in_sync']

class ReflectionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Reflection
        fields = ['id', 'pub_date', 'good', 'better', 'best', 'dreamstate']

class BoardSerializer(serializers.HyperlinkedModelSerializer):
    thread = ThreadSerializer(read_only=True)

    class Meta:
        model = Board
        fields = ['id', 'date_started', 'state', 'focus', 'thread']

class ObservationSerializer(serializers.HyperlinkedModelSerializer):
    type = serializers.SlugRelatedField(
        queryset=ObservationType.objects.all(),
        slug_field='slug'
    )

    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(),
        slug_field='name'
    )

    class Meta:
        model = Observation
        fields = ['id', 'pub_date', 'thread', 'type', 'situation', 'interpretation', 'approach', 'date_closed']

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

### XXX TODO
class BoardSummary(object):
    def __init__(self, board):
        self.board = board

    def filter_tree(self, pred):
        return filter(pred, tree_iterator(self.board.state))

    def finished(self):
        return self.filter_tree(state('checked'))

    def postponed(self):
        return self.filter_tree(marker('postponedFor'))

    def finished_count(self):
        return ilen(self.finished())

    def postponed_count(self):
        return ilen(self.postponed())

    def task_count(self):
        return ilen(tree_iterator(self.board.state))

    def days(self):
        return (self.board.date_closed - self.board.date_started).days

    def observations(self):
        # XXX TODO optimize N-question problem

        # XXX TODO hack
        if self.board.thread.name != 'Daily':
            return []

        return Observation.objects.filter(pub_date__range=(
            self.board.date_started, 
            self.board.date_closed
        ))