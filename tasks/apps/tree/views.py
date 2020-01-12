from django.shortcuts import render

from rest_framework import viewsets

from .serializers import BoardSerializer, BoardSummary, ThreadSerializer, PlanSerializer, ReflectionSerializer
from .models import Board, Thread, Plan, Reflection

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view

from django.utils import timezone
from django.shortcuts import get_object_or_404

import datetime

class BoardViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """

    def get_queryset(self):
        queryset = Board.objects.all()
        thread_id = self.request.query_params.get('thread', None)

        if thread_id is not None:
            queryset = queryset.filter(thread_id=thread_id)

        return queryset

    serializer_class = BoardSerializer

class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer

class ReflectionViewSet(viewsets.ModelViewSet):
    queryset = Reflection.objects.all()
    serializer_class = ReflectionSerializer

class ThreadViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """
    queryset = Thread.objects.all()
    serializer_class = ThreadSerializer

def transition_markers_in_tree_item(markers):
    return {
        "weeksInList": 0 if markers.get('madeProgress', False) else markers['weeksInList'] + 1,
        "important": markers['important'],
        "finalizing": markers['finalizing'],
        "canBeDoneOutsideOfWork": markers['canBeDoneOutsideOfWork'],
        "canBePostponed": markers['canBePostponed'],
        "postponedFor": max(0, markers['postponedFor'] - 1),
        "madeProgress": False,
    }

def transition_data_in_tree_item(item):
    return {
        "text": item['text'],
        "children": transition_data_between_boards(item['children']),

        "data": {
            "text": item['data']['text'],
            "state": item['data']['state'],
            "meaningfulMarkers": transition_markers_in_tree_item(item['data']['meaningfulMarkers']),
        },

        'state': {
            'visible': True if item['data']['meaningfulMarkers']['postponedFor'] == 1 else item['state']['visible']
        }
    }

def transition_data_between_boards(state):
    items = filter(lambda x: not x.get('state', {'checked': False })['checked'], state)

    return list(map(transition_data_in_tree_item, items))

@api_view(['POST'])
def commit_board(request, id=None):
    board = Board.objects.get(pk=id)

    new_board = Board()
    new_board.thread = board.thread

    new_board.state = transition_data_between_boards(board.state)
    board.date_closed = timezone.now()

    board.save()
    new_board.save()

    return Response(BoardSerializer(new_board).data)

def board_summary(request, id):
    board = get_object_or_404(Board, pk=id)

    summary = BoardSummary(board)

    return render(request, 'summary.html', {
        'board': board,
        'summary': summary,
    })

def period_from_request(request, days=7):
    return (
        request.GET.get('from', datetime.date.today() - datetime.timedelta(days=days)),
        request.GET.get('to', datetime.date.today())
    )


# XXX this does not account for missing day entries
# as of now this is not required. However, it might change
# solution: wrap plans and reflections with additional period-aware utility iterator
class Periodical:
    def __init__(self, plans, reflections):
        self.plans = plans
        self.reflections = reflections

    def __iter__(self):
        return zip(self.plans, self.reflections)

    def __len__(self):
        return len(self.plans)

    def __getattr__(self, attr):
        attr1, attr2 = attr.split('__')

        return map(lambda x: getattr(x, attr2), getattr(self, attr1 + 's'))


def periodical(request):
    period = period_from_request(request)

    plans = Plan.objects.filter(pub_date__range=period) \
        .order_by('pub_date') \
        .select_related('thread')

    reflections = Reflection.objects.filter(pub_date__range=period) \
        .order_by('pub_date') \
        .select_related('thread')

    thread = request.GET.get('thread')

    if thread:
        plans = plans.filter(thread_id=thread)
        reflections = reflections.filter(thread_id=thread)

    view = request.GET.get('view', 'list')

    if view not in ('list', 'table'):
        view = 'list'

    template = 'periodical_{}.html'.format(view)

    return render(request, template, {
        'plans': plans,
        'reflections': reflections,
        'combined': Periodical(plans, reflections),
    })