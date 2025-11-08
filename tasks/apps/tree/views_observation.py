from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from datetime import date

from rest_framework import viewsets, status
from rest_framework.response import Response as RestResponse
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination

from django.utils import timezone
from django.views.generic.list import ListView
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.forms import inlineformset_factory
from django.urls import reverse

from .models import (
    Observation,
    ObservationClosed,
    ObservationUpdated,
    ObservationType,
    Thread,
    Event,
    observation_event_types,
    ObservationAttached,
    ObservationDetached,
)
from .serializers import (
    ObservationSerializer,
    ObservationWithUpdatesSerializer,
    ObservationUpdatedSerializer,
    MultipleObservationUpdatedSerializer,
    ObservationEventSerializer,
    ObservationAttachedSerializer,
    ObservationDetachedSerializer,
    spawn_observation_events,
)
from .forms import ObservationForm
from .observation_operations import migrate_observation_updates_to_journal as _migrate_observation_updates_to_journal
from .presenters import get_complex_presenter


class ObservationPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class ObservationFilter(filters.FilterSet):
    OWNERSHIP_CHOICES = [
        ('all', 'All observations'),
        ('mine', 'My observations'),
    ]

    ownership = filters.ChoiceFilter(
        choices=OWNERSHIP_CHOICES,
        method='filter_ownership',
        empty_label='All observations',
        label='Show'
    )

    def filter_ownership(self, queryset, name, value):
        if value == 'mine':
            return queryset.filter(user=self.request.user)
        return queryset

    class Meta:
        model = Observation
        fields = {
            'pub_date': ('gte', 'lte'),
            'event_stream_id': ('exact',)
        }


class EventFilter(filters.FilterSet):
    open = filters.BooleanFilter(method='filter_open')

    def filter_open(self, queryset, name, value):
        if value is None:
            return queryset

        return queryset.annotate(
            is_open=Exists(Observation.objects.filter(event_stream_id=OuterRef('event_stream_id')))
        ).filter(is_open=value)

    class Meta:
        model = Event
        fields = {
            'published': ('gte', 'lte'),
            'event_stream_id': ('exact',),
        }


class ObservationViewSet(viewsets.ModelViewSet):
    queryset = Observation.objects.with_last_event_published()

    filter_backends = [DjangoFilterBackend]
    filter_class = ObservationFilter

    pagination_class = ObservationPagination

    def get_serializer_class(self):
        features = self.request.query_params.get('features')

        if features and 'updates' in features:
            return ObservationWithUpdatesSerializer

        return ObservationSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ObservationUpdatedViewSet(viewsets.ModelViewSet):
    queryset = ObservationUpdated.objects.order_by('published')

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['observation_id']

    def get_serializer_class(self):
        if self.request.query_params.get('observation_id'):
            return MultipleObservationUpdatedSerializer

        return ObservationUpdatedSerializer


class ObservationEventViewSet(viewsets.ModelViewSet):
    # XXX do we need to filter out events that are not of the observation type?
    queryset = Event.objects.instance_of(
        *observation_event_types
    )

    serializer_class = ObservationEventSerializer

    filter_backends = [DjangoFilterBackend]
    filter_class = EventFilter


class ObservationListView(LoginRequiredMixin, ListView):
    model = Observation
    queryset = Observation.objects \
        .select_related('thread', 'type') \
        .prefetch_related('observationupdated_set')

    paginate_by = 200

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = Observation.objects.count()
        context['closed_count'] = ObservationClosed.objects.count()
        context['mine_count'] = Observation.objects.filter(user=self.request.user).count()

        # Add attach mode context
        context['attach_mode'] = self.request.GET.get('attach_mode') == 'true'
        context['attach_observation_id'] = self.request.GET.get('observation_id')

        return context


class ObservationClosedListView(LoginRequiredMixin, ListView):
    model = ObservationClosed
    queryset = ObservationClosed.objects \
        .select_related('thread', 'type') \
        .order_by('-published')

    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = Observation.objects.count()
        context['closed_count'] = ObservationClosed.objects.count()
        context['mine_count'] = Observation.objects.filter(user=self.request.user).count()

        return context


class ObservationMineListView(LoginRequiredMixin, ListView):
    model = Observation
    template_name = 'tree/observation_list.html'
    paginate_by = 200

    def get_queryset(self):
        return Observation.objects \
            .filter(user=self.request.user) \
            .select_related('thread', 'type') \
            .prefetch_related('observationupdated_set') \
            .order_by('-pub_date', '-pk')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = Observation.objects.count()
        context['closed_count'] = ObservationClosed.objects.count()
        context['mine_count'] = Observation.objects.filter(user=self.request.user).count()

        # Add attach mode context
        context['attach_mode'] = self.request.GET.get('attach_mode') == 'true'
        context['attach_observation_id'] = self.request.GET.get('observation_id')

        return context


class LessonsListView(LoginRequiredMixin, ListView):
    model = ObservationClosed
    template_name = 'tree/lessons_list.html'
    paginate_by = 100

    def get_queryset(self):
        return ObservationClosed.objects \
            .select_related('thread', 'type') \
            .exclude(approach__isnull=True) \
            .exclude(approach__exact='') \
            .exclude(approach__exact='?') \
            .order_by('-published')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = Observation.objects.count()
        context['closed_count'] = ObservationClosed.objects.count()
        context['mine_count'] = Observation.objects.filter(user=self.request.user).count()

        return context


@login_required
def observation_closed_detail(request, event_stream_id):
    observation_closed = get_object_or_404(ObservationClosed, event_stream_id=event_stream_id)

    events = list(Event.objects.filter(
        event_stream_id=observation_closed.event_stream_id
    ).order_by('published'))

    time_to_closed = events[-1].published - events[0].published

    return render(request, 'tree/observationclosed_detail.html', {
        'instance': observation_closed,
        'events': events,
        'updates': filter(lambda x: isinstance(x, ObservationUpdated), events),
        'time_to_closed': time_to_closed
    })


def _get_initial_dict_for_observation(observation):
    initial_dict = {}

    if not observation.pub_date:
        initial_dict['pub_date'] = date.today()

    if not observation.type_id:
        initial_dict['type'] = ObservationType.objects.get(name='Observation')

    if not observation.thread_id:
        initial_dict['thread'] = Thread.objects.get(name='big-picture')

    return initial_dict


@login_required
def observation_edit(request, observation_id=None):
    if observation_id is not None:
        observation = get_object_or_404(Observation, id=observation_id)
    else:
        observation = Observation()

    previous = observation.copy(as_new=False)

    ObservationUpdatedFormSet = inlineformset_factory(Observation, ObservationUpdated, fields=('comment',), extra=3)

    observation_updated_queryset = ObservationUpdated.objects.order_by('pk')

    if request.method == "POST":
        form = ObservationForm(request.POST, instance=observation)
        formset = ObservationUpdatedFormSet(
            request.POST,
            instance=observation,
            queryset=observation_updated_queryset,
        )

        now = timezone.now()

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                if not obj.pk:
                    obj.user = request.user
                obj.save()

                events = spawn_observation_events(previous, obj, published=now)
                for event in events:
                    event.save()

                updates = formset.save(commit=False)
                for update in updates:
                    if not update.pk:
                        update.published = now
                    update.save()

            if 'save_and_close' in request.POST:
                return redirect(reverse('public-observation-list'))

            return redirect(reverse('public-observation-edit', args=[observation.pk]))

    else:
        initial_dict = _get_initial_dict_for_observation(observation)

        form = ObservationForm(instance=observation, initial=initial_dict)
        formset = ObservationUpdatedFormSet(
            instance=observation,
            queryset=observation_updated_queryset,
        )

    return render(request, "tree/observation_edit.html", {
        "events": observation.get_events(),
        "form": form,
        "formset": formset,
        "instance": observation,
        "thread_as_link": True,
        "complex_presenter": get_complex_presenter(observation),
    })


@api_view(['POST'])
def observation_close(request, observation_id):
    observation = get_object_or_404(Observation, pk=observation_id)

    observation_closed = ObservationClosed.from_observation(observation)

    with transaction.atomic():
        observation_closed.save()

        observation.delete()

    response = RestResponse({'ok': True}, status=status.HTTP_200_OK)
    response['HX-Redirect'] = reverse('public-observation-list')

    return response


@api_view(['POST'])
def migrate_observation_updates_to_journal(request, observation_id):
    observation = get_object_or_404(Observation, pk=observation_id)
    thread = Thread.objects.get(name='Daily')

    _migrate_observation_updates_to_journal(observation, thread.id)

    if request.htmx:
        response = RestResponse({'ok': True}, status=status.HTTP_200_OK)
        response['HX-Redirect'] = reverse('public-observation-list')

        return response

    return redirect(reverse('public-observation-list'))


@api_view(['POST'])
def observation_attach(request, observation_id):
    """Attach another observation to this observation (making it a complex observation)"""
    complex_observation = get_object_or_404(Observation, pk=observation_id)

    # Get the observation to attach - can be either observation_id or event_stream_id
    other_observation_id = request.data.get('other_observation_id')
    other_event_stream_id = request.data.get('other_event_stream_id')

    if not other_observation_id and not other_event_stream_id:
        return RestResponse(
            {'error': 'Either other_observation_id or other_event_stream_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Find the other observation
    other_observation = None
    if other_observation_id:
        try:
            other_observation = Observation.objects.get(pk=other_observation_id)
            other_event_stream_id = other_observation.event_stream_id
        except Observation.DoesNotExist:
            return RestResponse(
                {'error': 'Observation to attach does not exist'},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        # Try to find by event_stream_id (might be a closed observation)
        try:
            other_observation = Observation.objects.get(event_stream_id=other_event_stream_id)
        except Observation.DoesNotExist:
            # It's okay if observation doesn't exist (could be closed)
            other_observation = None

    # Check if the observation is already attached by replaying events
    from .presenters import ComplexPresenter
    complex_presenter = ComplexPresenter(complex_observation.event_stream_id)

    if complex_presenter.is_attached(other_event_stream_id):
        # Already attached, find the most recent attach event and return it
        latest_attach_event = ObservationAttached.objects.filter(
            event_stream_id=complex_observation.event_stream_id,
            other_event_stream_id=other_event_stream_id
        ).order_by('-published').first()

        if latest_attach_event:
            serializer = ObservationAttachedSerializer(latest_attach_event, context={'request': request})
            return RestResponse(serializer.data, status=status.HTTP_201_CREATED)

    # Create the attach event
    attach_event = ObservationAttached(
        thread=complex_observation.thread,
        event_stream_id=complex_observation.event_stream_id,
        other_event_stream_id=other_event_stream_id,
        observation=other_observation
    )
    attach_event.save()

    serializer = ObservationAttachedSerializer(attach_event, context={'request': request})
    return RestResponse(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def observation_detach(request, observation_id):
    """Detach an observation from this complex observation"""
    complex_observation = get_object_or_404(Observation, pk=observation_id)

    # Get the event_stream_id to detach
    other_event_stream_id = request.data.get('other_event_stream_id')
    if not other_event_stream_id:
        return RestResponse(
            {'error': 'other_event_stream_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if the observation is currently attached by replaying events
    from .presenters import ComplexPresenter
    complex_presenter = ComplexPresenter(complex_observation.event_stream_id)

    if not complex_presenter.is_attached(other_event_stream_id):
        # Not attached, find the most recent detach event and return it
        latest_detach_event = ObservationDetached.objects.filter(
            event_stream_id=complex_observation.event_stream_id,
            other_event_stream_id=other_event_stream_id
        ).order_by('-published').first()

        if latest_detach_event:
            serializer = ObservationDetachedSerializer(latest_detach_event, context={'request': request})
            return RestResponse(serializer.data, status=status.HTTP_201_CREATED)

    # Create the detach event
    detach_event = ObservationDetached(
        thread=complex_observation.thread,
        event_stream_id=complex_observation.event_stream_id,
        other_event_stream_id=other_event_stream_id
    )
    detach_event.save()

    serializer = ObservationDetachedSerializer(detach_event, context={'request': request})
    return RestResponse(serializer.data, status=status.HTTP_201_CREATED)


def filter_out_attached_observations(observations, observation_id):
    """
    Filter out observations that are already attached to the given observation,
    including the base observation itself.
    """
    if not observation_id:
        return observations

    try:
        base_observation = Observation.objects.get(pk=observation_id)
        from .presenters import ComplexPresenter
        complex_presenter = ComplexPresenter(base_observation.event_stream_id)
        attached_stream_ids = complex_presenter.get_attached_stream_ids()

        # Exclude the base observation itself and any attached observations
        observations = observations.exclude(pk=observation_id)
        if attached_stream_ids:
            observations = observations.exclude(event_stream_id__in=attached_stream_ids)
    except Observation.DoesNotExist:
        pass  # If observation doesn't exist, proceed without filtering

    return observations


@api_view(['GET'])
def observation_search(request):
    """Search observations by situation, interpretation, and approach text fields, or by primary key pattern"""
    query = request.GET.get('q', '').strip()
    observation_id = request.GET.get('observation')  # Optional parameter to filter out attached observations

    if not query:
        return RestResponse(
            {'error': 'Query parameter "q" is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Check if query is a primary key pattern search (numeric or #numeric)
    pk_query = query
    if query.startswith('#'):
        pk_query = query[1:]

    if pk_query.isdigit():
        # Search by primary key pattern - find PKs that start with the number
        observations = Observation.objects.with_last_event_published().extra(
            where=["CAST(id AS TEXT) LIKE %s"],
            params=[pk_query + '%']
        ).order_by('id')

        # Filter out attached observations if observation_id is provided
        observations = filter_out_attached_observations(observations, observation_id)

        # Apply pagination
        paginator = ObservationPagination()
        page = paginator.paginate_queryset(observations, request)

        if page is not None:
            serializer = ObservationSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        serializer = ObservationSerializer(observations, many=True, context={'request': request})
        return RestResponse({
            'count': len(observations),
            'next': None,
            'previous': None,
            'results': serializer.data
        })

    # Create search vectors with different weights
    # Situation field gets higher weight (A = highest weight)
    # Interpretation and approach get lower weight (B)
    search_vector = (
        SearchVector('situation', weight='A') +
        SearchVector('interpretation', weight='B') +
        SearchVector('approach', weight='B')
    )

    search_query = SearchQuery(query)

    # Search observations and rank by relevance
    observations = Observation.objects.with_last_event_published().annotate(
        search=search_vector,
        rank=SearchRank(search_vector, search_query)
    ).filter(
        search=search_query
    ).order_by('-rank', '-pub_date')

    # Filter out attached observations if observation_id is provided
    observations = filter_out_attached_observations(observations, observation_id)

    # Apply pagination
    paginator = ObservationPagination()
    page = paginator.paginate_queryset(observations, request)

    if page is not None:
        serializer = ObservationSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    serializer = ObservationSerializer(observations, many=True, context={'request': request})
    return RestResponse(serializer.data)


@api_view(['GET'])
def observation_attachments(request, observation_id):
    """Get all currently attached observations for a given observation"""
    complex_observation = get_object_or_404(Observation, pk=observation_id)

    from .presenters import ComplexPresenter
    complex_presenter = ComplexPresenter(complex_observation.event_stream_id)

    # Get all currently attached stream IDs
    attached_stream_ids = complex_presenter.get_attached_stream_ids()

    # Return the list of stream IDs for frontend processing
    return RestResponse({
        'attached_observation_stream_ids': list(attached_stream_ids),
        'count': len(attached_stream_ids)
    })
