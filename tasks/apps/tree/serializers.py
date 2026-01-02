from functools import partial
from operator import itemgetter

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from rest_framework import serializers
from rest_polymorphic.serializers import PolymorphicSerializer

from .models import *
from .templatetags.model_presenters import first_line


class ThreadSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Thread
        fields = ["id", "name"]


class HabitSerializer(serializers.HyperlinkedModelSerializer):
    today_tracked = serializers.IntegerField(read_only=True)
    keywords = serializers.SerializerMethodField()

    def get_keywords(self, obj):
        return list(obj.get_keywords())

    class Meta:
        model = Habit
        fields = ["id", "name", "description", "slug", "keywords", "today_tracked"]


class HabitKeywordSerializer(serializers.ModelSerializer):
    habit = HabitSerializer(read_only=True)

    class Meta:
        model = HabitKeyword
        fields = ["id", "keyword", "habit"]


class ProfileSerializer(serializers.ModelSerializer):
    default_board_thread = ThreadSerializer(read_only=True)
    habit_keywords = HabitKeywordSerializer(many=True, read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "default_board_thread", "habit_keywords"]


class PlanSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "pub_date", "want", "focus"]


class ReflectionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Reflection
        fields = ["id", "pub_date", "good", "better", "best"]


class BoardSerializer(serializers.HyperlinkedModelSerializer):
    thread = ThreadSerializer(read_only=True)

    class Meta:
        model = Board
        fields = ["id", "date_started", "state", "focus", "thread"]


class JournalTagSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = JournalTag
        fields = ["id", "name", "slug"]


def spawn_observation_events(previous, current, published=None):
    if not published:
        published = timezone.now()

    def was_changed(x):
        new = getattr(current, x)
        old = getattr(previous, x)

        not_changing_null_into_empty = bool(old) or bool(new)

        same_excluding_whitespace = type(old) == type(
            new
        ) == str and old.strip().replace("\r", "") == new.strip().replace("\r", "")

        return (
            old != new
            and not_changing_null_into_empty
            and not same_excluding_whitespace
        )

    def was_set(x):
        return getattr(previous, x) is None and getattr(current, x) is not None

    def filter_func(t):
        x, f = t

        return f(x)

    changed_checks = [
        ("pk", was_set),
        ("situation", was_changed),
        ("interpretation", was_changed),
        ("approach", was_changed),
    ]

    changed_data = list(map(itemgetter(0), filter(filter_func, changed_checks)))

    if "pk" in changed_data:
        observation_made = ObservationMade.from_observation(
            current, published=published
        )

        return [observation_made]

    events = []

    if "situation" in changed_data:
        obj = ObservationRecontextualized.from_observation(
            current, previous.situation, published=published
        )
        events.append(obj)

    if "interpretation" in changed_data:
        obj = ObservationReinterpreted.from_observation(
            current, previous.interpretation, published=published
        )
        events.append(obj)

    if "approach" in changed_data:
        obj = ObservationReflectedUpon.from_observation(
            current, previous.approach, published=published
        )
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
        queryset=ObservationType.objects.all(), slug_field="slug"
    )

    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(), slug_field="name"
    )


class ObservationUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "username"]


class ObservationSerializer(BaseTypeThreadSerializer):
    user = ObservationUserSerializer(read_only=True)
    last_event_published = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Observation
        fields = [
            "id",
            "pub_date",
            "thread",
            "type",
            "situation",
            "interpretation",
            "approach",
            "user",
            "last_event_published",
        ]

    @transaction.atomic
    def save(self, *args, **kwargs):
        old_obj = get_unsaved_object(Observation, self.instance)
        new_obj = super().save(*args, **kwargs)

        events = spawn_observation_events(old_obj, new_obj, published=timezone.now())

        for event in events:
            event.save()

        return new_obj


class ObservationUpdatedSerializer(serializers.ModelSerializer):
    observation_fields = ObservationSerializer(read_only=True)

    class Meta:
        model = ObservationUpdated
        fields = ["id", "comment", "published", "observation_fields", "observation"]


class MultipleObservationUpdatedSerializer(serializers.ModelSerializer):

    class Meta:
        model = ObservationUpdated
        fields = ["id", "comment", "published", "event_stream_id"]


class ObservationWithUpdatesSerializer(ObservationSerializer):
    updates = MultipleObservationUpdatedSerializer(
        many=True, read_only=True, source="observationupdated_set"
    )

    class Meta(ObservationSerializer.Meta):
        fields = ObservationSerializer.Meta.fields + ["updates"]


class JournalAddedSerializer(serializers.ModelSerializer):
    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(), slug_field="name"
    )

    tags = serializers.SlugRelatedField(
        many=True,
        queryset=JournalTag.objects.all(),
        slug_field="slug",
    )

    class Meta:
        model = JournalAdded
        fields = ["id", "comment", "published", "thread", "tags"]


class QuickNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuickNote
        fields = ["id", "published", "note"]


class ObservationMadeSerializer(BaseTypeThreadSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        if "request" in self.context:
            return self.context["request"].build_absolute_uri(obj.url())

        return obj.url()

    class Meta:
        model = ObservationMade
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "type",
            "situation",
            "interpretation",
            "approach",
            "url",
        ]


class ObservationRecontextualizedSerializer(BaseTypeThreadSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        if "request" in self.context:
            return self.context["request"].build_absolute_uri(obj.url())

        return obj.url()

    class Meta:
        model = ObservationRecontextualized
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "situation",
            "old_situation",
            "url",
        ]


class ObservationReinterpretedSerializer(BaseTypeThreadSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        if "request" in self.context:
            return self.context["request"].build_absolute_uri(obj.url())

        return obj.url()

    class Meta:
        model = ObservationReinterpreted
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "interpretation",
            "old_interpretation",
            "situation_at_creation",
            "url",
        ]


class ObservationReflectedUponSerializer(BaseTypeThreadSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        if "request" in self.context:
            return self.context["request"].build_absolute_uri(obj.url())

        return obj.url()

    class Meta:
        model = ObservationReflectedUpon
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "approach",
            "old_approach",
            "situation_at_creation",
            "url",
        ]


class ObservationClosedSerializer(BaseTypeThreadSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        if "request" in self.context:
            return self.context["request"].build_absolute_uri(obj.url())

        return obj.url()

    class Meta:
        model = ObservationClosed
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "type",
            "situation",
            "interpretation",
            "approach",
            "url",
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


class HabitTrackedSerializer(serializers.ModelSerializer):
    habit = HabitSerializer(read_only=True)

    class Meta:
        model = HabitTracked
        fields = ["id", "published", "habit", "occured", "note"]


class ProjectedOutcomeMadeSerializer(serializers.ModelSerializer):
    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(), slug_field="name"
    )

    class Meta:
        model = ProjectedOutcomeMade
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "name",
            "description",
            "resolved_by",
            "success_criteria",
        ]


class ProjectedOutcomeRedefinedSerializer(serializers.ModelSerializer):
    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(), slug_field="name"
    )

    class Meta:
        model = ProjectedOutcomeRedefined
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "old_name",
            "new_name",
            "old_description",
            "new_description",
            "old_success_criteria",
            "new_success_criteria",
        ]


class ProjectedOutcomeRescheduledSerializer(serializers.ModelSerializer):
    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(), slug_field="name"
    )

    class Meta:
        model = ProjectedOutcomeRescheduled
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "old_resolved_by",
            "new_resolved_by",
        ]


class ProjectedOutcomeClosedSerializer(serializers.ModelSerializer):
    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(), slug_field="name"
    )

    class Meta:
        model = ProjectedOutcomeClosed
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "name",
            "description",
            "resolved_by",
            "success_criteria",
        ]


def get_observation_object(obj):
    if obj.observation:
        return obj.observation

    return ObservationMade.objects.get(event_stream_id=obj.event_stream_id)


class ObservationUpdatedEventSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    def get_url(self, obj):
        if "request" in self.context:
            return self.context["request"].build_absolute_uri(obj.url())

        return obj.url()

    class Meta:
        model = ObservationUpdated
        fields = [
            "id",
            "comment",
            "published",
            "event_stream_id",
            "observation_id",
            "situation_at_creation",
            "url",
        ]


class ObservationAttachedSerializer(serializers.ModelSerializer):
    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(), slug_field="name"
    )

    class Meta:
        model = ObservationAttached
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "other_event_stream_id",
            "observation",
        ]


class ObservationDetachedSerializer(serializers.ModelSerializer):
    thread = serializers.SlugRelatedField(
        queryset=Thread.objects.all(), slug_field="name"
    )

    class Meta:
        model = ObservationDetached
        fields = [
            "id",
            "published",
            "event_stream_id",
            "thread",
            "other_event_stream_id",
        ]


class EventSerializer(PolymorphicSerializer):
    model_serializer_mapping = {
        ObservationMade: ObservationMadeSerializer,
        ObservationRecontextualized: ObservationRecontextualizedSerializer,
        ObservationReinterpreted: ObservationReinterpretedSerializer,
        ObservationReflectedUpon: ObservationReflectedUponSerializer,
        ObservationClosed: ObservationClosedSerializer,
        ObservationUpdated: ObservationUpdatedEventSerializer,
        ObservationAttached: ObservationAttachedSerializer,
        ObservationDetached: ObservationDetachedSerializer,
        JournalAdded: JournalAddedSerializer,
        HabitTracked: HabitTrackedSerializer,
        ProjectedOutcomeMade: ProjectedOutcomeMadeSerializer,
        ProjectedOutcomeRedefined: ProjectedOutcomeRedefinedSerializer,
        ProjectedOutcomeRescheduled: ProjectedOutcomeRescheduledSerializer,
        ProjectedOutcomeClosed: ProjectedOutcomeClosedSerializer,
    }


class tree_iterator:
    """Preorder traversal tree iterator"""

    def __init__(self, tree, key="children"):
        self.key = key

        # Internally this iterator requires top-level list,
        # so if given a valid node (that has children key)
        # wrap it in a list
        if key in tree:
            tree = [tree]

        self.iterators = [iter(tree)]

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
    return item.get("state", {}).get(key, default)


def state(key, default=None):
    return partial(_state, key, default)


def _marker(key, default, item):
    return item.get("data", {}).get("meaningfulMarkers", {}).get(key, default)


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
        return self.filter_tree(state("checked"))

    def postponed(self):
        return self.filter_tree(marker("postponedFor"))

    def removed(self):
        weeks_in_list = marker("weeksInList")
        checked = state("checked")
        postponed_for = marker("postponedFor")
        made_progress = marker("madeProgress")

        return self.filter_tree(
            lambda item: weeks_in_list(item) >= 5
            and not checked(item)
            and postponed_for(item) == 0
            and not made_progress(item)
        )

    def finished_count(self):
        return ilen(self.finished())

    def postponed_count(self):
        return ilen(self.postponed())

    def removed_count(self):
        return ilen(self.removed())

    def task_count(self):
        return ilen(tree_iterator(self.board.before))

    def days(self):
        return (self.board.published - self.board.date_started).days
