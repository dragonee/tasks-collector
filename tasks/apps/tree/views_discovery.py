from rest_framework.decorators import api_view
from rest_framework.response import Response as RestResponse
from rest_framework import status, viewsets

from .models import Event, JournalAdded, observation_event_types, HabitTracked, Discovery, ProjectedOutcomeMade, ProjectedOutcomeRedefined, ProjectedOutcomeRescheduled, ProjectedOutcomeClosed
from .serializers import EventSerializer, DiscoveryEventsRequestSerializer, DiscoverySerializer

journal_event_types = [
    JournalAdded
]

other_event_types = [
    HabitTracked,
    Discovery,
    ProjectedOutcomeMade,
    ProjectedOutcomeRedefined,
    ProjectedOutcomeRescheduled,
    ProjectedOutcomeClosed
]

journal_event_type_mapping = {
    'journal': journal_event_types,
    'observation': observation_event_types,
    'other': other_event_types
}

def filter_events_by_types(qs, event_types):
    if not event_types or not isinstance(event_types, list):
        return qs

    type_filters = []

    for event_type in event_types:
        type_filters.extend(journal_event_type_mapping[event_type])

    if not type_filters:
        return qs

    return qs.instance_of(*type_filters)


@api_view(['POST'])
def discovery_events(request):

    # Validate request data
    request_serializer = DiscoveryEventsRequestSerializer(data=request.data)
    if not request_serializer.is_valid():
        return RestResponse(
            request_serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    # Extract validated data
    validated_data = request_serializer.validated_data
    number = validated_data.get('number', 3)
    events_param = validated_data.get('events')
    from_datetime = validated_data.get('from')
    to_datetime = validated_data.get('to')
    event_types = validated_data.get('type', ['journal', 'observation', 'other'])

    # Build base queryset
    queryset = Event.objects.filter(
        published__gte=from_datetime,
        published__lte=to_datetime
    )

    # Filter by event types if specified
    queryset = filter_events_by_types(queryset, event_types)
    
    locked_event_ids = [x for x in events_param if x is not None]
    locked_events_count = len(locked_event_ids)
    random_events_count = number - locked_events_count

    random_events = list(queryset.exclude(
        id__in=locked_event_ids
    ).order_by('?')[:random_events_count])

    if len(random_events) < random_events_count:
        return RestResponse(
            {'error': f'Not enough events available. Requested {random_events_count}, found {len(random_events)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    locked_events = {event.id: event for event in Event.objects.filter(id__in=locked_event_ids)}

    if len(locked_events) < locked_events_count:
        return RestResponse(
            {'error': f'Some requested events do not exist. Requested {locked_event_ids}, found {len(locked_events)}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    result_events = []

    for event_id in events_param:
        if event_id is None:
            result_events.append(random_events.pop(0))
        else:
            result_events.append(locked_events[event_id])
        
    serializer = EventSerializer(result_events, many=True, context={'request': request})
    
    return RestResponse({
        'count': len(result_events),
        'events': serializer.data
    }, status=status.HTTP_200_OK)


class DiscoveryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for creating, reading, updating, and deleting Discovery items.
    Similar to ObservationUpdatedViewSet.
    """
    queryset = Discovery.objects.order_by('-published')
    serializer_class = DiscoverySerializer
