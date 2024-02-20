from django.shortcuts import render, redirect

from rest_framework import viewsets
from rest_framework import status


from .serializers import BoardSerializer, BoardSummary, ThreadSerializer, PlanSerializer, ReflectionSerializer, ObservationSerializer
from .models import Board, Thread, Plan, Reflection, Observation
from .forms import PlanForm, ReflectionForm

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view

from django.utils import timezone
from django.shortcuts import get_object_or_404

from django.views.generic.list import ListView

from functools import reduce, partial
from collections import OrderedDict

from itertools import groupby

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend


from copy import deepcopy

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

class ObservationFilter(filters.FilterSet):
    class Meta:
        model = Observation
        fields = {
            'pub_date': ('gte', 'lte'),
            'date_closed': ('isnull', ),
        }

class ObservationViewSet(viewsets.ModelViewSet):
    queryset = Observation.objects.all()
    serializer_class = ObservationSerializer

    filter_backends = [DjangoFilterBackend]
    filter_class = ObservationFilter

class ThreadViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """
    queryset = Thread.objects.all()
    serializer_class = ThreadSerializer

def transition_markers_in_tree_item(markers):
    new_markers = {
        "weeksInList": 0 if markers.get('madeProgress', False) else markers['weeksInList'] + 1,
        "important": markers['important'],
        "finalizing": markers['finalizing'],
        "canBeDoneOutsideOfWork": markers['canBeDoneOutsideOfWork'],
        "canBePostponed": markers['canBePostponed'],
        "postponedFor": max(0, markers['postponedFor'] - 1),
        "madeProgress": False,
    }

    value = markers.get('transition')

    if value:
        new_markers['transition'] = value

    return new_markers

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

def filter_out_checked_items(x):
    """Return True if should be filtered out"""

    if x.get('data', {}).get('meaningfulMarkers', {}).get('canBePostponed', False):
        return False

    return x.get('state', {}).get('checked', False)


def transition_data_between_boards(state):
    items = filter(lambda x: not filter_out_checked_items(x), state)

    return list(map(transition_data_in_tree_item, items))

def recursively(collection, f, c, key='children'):
    return c([c((recursively(item[key], f, c), f(item))) for item in collection])

def unionize_sets(items):
    return reduce(lambda x, y: x.union(y if isinstance(y, set) else set([y])), items, set())

def make_board(thread_name):
    thread=Thread.objects.get(name=thread_name)

    try:
        return Board.objects.filter(thread=thread)[0]
    except IndexError:
        return Board(thread=thread)

def cut_leaves(board_state, thread_name, implied=False):
    new_board_state = []

    for item in board_state:
        # None or string
        item_thread_name = item['data']['meaningfulMarkers'].get('transition')

        new_implied = item_thread_name or implied

        children = cut_leaves(item['children'], thread_name, implied=new_implied)

        if children or (item_thread_name == thread_name and implied == False) or implied == thread_name:
            try:
                del item['data']['meaningfulMarkers']['transition']
            except KeyError:
                pass

            new_board_state.append(item)

        item['children'] = children

    return new_board_state

def merge(a, b):
    names_a = OrderedDict((item['data']['text'], index) for index,item in enumerate(a))

    names_b = OrderedDict((item['data']['text'], index) for index,item in enumerate(b))

    print(names_a, names_b)

    common = set(names_a.keys()).intersection(names_b.keys())

    in_b = set(names_b.keys()).difference(names_a.keys())

    for key in common:
        item_a = a[names_a[key]]
        item_b = b[names_b[key]]

        item_a['children'] = merge(item_a['children'], item_b['children'])

    return a + [b[names_b[key]] for key in in_b]

def pprint(board_state, level=0):
    for item in board_state:
        print("  " * level, item['data']['text'], flush=True)
        pprint(item['children'], level + 1)

@api_view(['POST'])
def commit_board(request, id=None):
    board = Board.objects.get(pk=id)

    new_board = Board()
    new_board.thread = board.thread

    new_board.state = transition_data_between_boards(board.state)
    # recursively find all boards referenced by "transition fields"
    thread_names = recursively(
        new_board.state,
        lambda item: item['data']['meaningfulMarkers'].get('transition'),
        unionize_sets
    )

    other_boards = list(map(make_board, thread_names.difference({None})))

    # dfs with leaf-cutting
    for other_board in other_boards:
        other_board.state = merge(other_board.state, cut_leaves(deepcopy(new_board.state), other_board.thread.name))


    #print(thread_names.difference({None}))
    new_board.state = cut_leaves(new_board.state, None)

    # merge boards
    for other_board in other_boards:
        #print("Board ({})".format(other_board.thread.name))
        #pprint(other_board.state)
        #print('------------------', flush=True)
        other_board.save()

    #pprint(new_board.state)

    board.date_closed = timezone.now()
    board.save()
    new_board.save()

    return Response(BoardSerializer(new_board).data)

@api_view(['POST'])
def add_task(request):
    item = request.data

    # XXX hackish
    if not 'text' in item or not 'thread-name' in item:
        return Response({'errors': 'no thread-name and text'}, status=status.HTTP_400_BAD_REQUEST)
    
    thread = get_object_or_404(Thread, name=item['thread-name'])
    board = Board.objects.filter(thread=thread).order_by('-date_started').first()

    board.state.append({
        'children': [],
        'data': {
            'state': 'open',
            'text': item['text'],
            'meaningfulMarkers': {
                "weeksInList": 0,
                "important": False,
                "finalizing": False,
                "canBeDoneOutsideOfWork": False,
                "canBePostponed": False,
                "postponedFor": 0,
                "madeProgress": False,
            }
        },
        'text': item['text'],
    })

    board.save()

    return Response(BoardSerializer(board).data)


def board_summary(request, id):
    board = get_object_or_404(Board, pk=id)

    summary = BoardSummary(board)

    return render(request, 'summary.html', {
        'boards': [board],
        'summaries': [summary],
    })

def period_from_request(request, days=7, start=None, end=None):
    return (
        request.GET.get('from', start or datetime.date.today() - datetime.timedelta(days=days)),
        request.GET.get('to', end or datetime.date.today() + datetime.timedelta(days=1))
    )

def summaries(request):
    period = period_from_request(request, days=30)

    boards = Board.objects.filter(date_closed__range=period).order_by('-date_closed')

    if boards.count() == 0:
        boards = Board.objects.filter(date_closed__isnull=False).order_by('-date_closed')[:1]

    summaries = [BoardSummary(board) for board in boards]

    return render(request, 'summary.html', {
        'boards': boards,
        'summaries': summaries,
    })

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
    try:
        last_big_picture_reflection = Reflection.objects.filter(
            thread__name='big-picture'
        ).order_by('-pub_date')[0]

        start_date = min([
            last_big_picture_reflection.pub_date,
            datetime.date.today() - datetime.timedelta(days=14)
        ])

        period = period_from_request(
            request,
            start=start_date
        )
    except IndexError:
        period = period_from_request(
            request,
            days=14
        )

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
        'period': period,
        'plans': plans,
        'reflections': reflections,
        'combined': Periodical(plans, reflections),
    })

def today(request):
    if request.method == 'POST':
        thread_name = request.POST.get('thread')
    else:
        thread_name = request.GET.get('thread', 'Daily')

    thread = Thread.objects.get(name=thread_name)

    try:
        now = datetime.datetime.strptime(request.GET['date'], '%Y-%m-%d')
        today = now.date()
    except KeyError:
        now = timezone.now()

        today = now.date()

        if 0 <= now.hour < 12:
            today -= datetime.timedelta(days=1)

    try:
        today_plan = Plan.objects.get(pub_date=today, thread=thread)
    except Plan.DoesNotExist:
        today_plan = Plan(pub_date=today, thread=thread)

    tomorrow = today + datetime.timedelta(days=1)

    try:
        tomorrow_plan = Plan.objects.get(pub_date=tomorrow, thread=thread)
    except Plan.DoesNotExist:
        tomorrow_plan = Plan(pub_date=tomorrow, thread=thread)

    try:
        reflection = Reflection.objects.get(pub_date=today, thread=thread)
    except Reflection.DoesNotExist:
        reflection = Reflection(pub_date=today, thread=thread)

    if request.method == 'POST':
        today_plan_form = PlanForm(request.POST, instance=today_plan, prefix="today_plan")
        today_valid = today_plan_form.is_valid()

        if today_valid:
            today_plan_form.save()


        tomorrow_plan_form = PlanForm(request.POST, instance=tomorrow_plan, prefix="tomorrow_plan")
        tomorrow_valid = tomorrow_plan_form.is_valid()

        if tomorrow_valid:
            tomorrow_plan_form.save()

        reflection_form = ReflectionForm(request.POST, instance=reflection, prefix="reflection")
        reflection_valid = reflection_form.is_valid()

        if reflection_valid:
            reflection_form.save()

        if all((today_valid, tomorrow_valid, reflection_valid)):
            return redirect(request.get_full_path())

    else:
        today_plan_form = PlanForm(instance=today_plan, prefix="today_plan")
        tomorrow_plan_form = PlanForm(instance=tomorrow_plan, prefix="tomorrow_plan")
        reflection_form = ReflectionForm(instance=reflection, prefix="reflection")

    return render(request, 'today.html', {
        'yesterday': today - datetime.timedelta(days=1),
        'today': today,
        'tomorrow': today + datetime.timedelta(days=1),
        'today_plan': today_plan,
        'tomorrow_plan': tomorrow_plan,
        'reflection': reflection,

        'today_plan_form': today_plan_form,
        'tomorrow_plan_form': tomorrow_plan_form,
        'reflection_form': reflection_form,

        'thread': thread,
        'threads': Thread.objects.all(),
    })

class ObservationListView(ListView):
    model = Observation
    queryset = Observation.objects \
        .filter(date_closed__isnull=True) \
        .select_related('thread', 'type') \
        .prefetch_related('update_set')

    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = len(Observation.objects.filter(date_closed__isnull=True))
        context['closed_count'] = len(Observation.objects.filter(date_closed__isnull=False))

        return context

class ObservationClosedListView(ListView):
    model = Observation
    queryset = Observation.objects \
        .filter(date_closed__isnull=False) \
        .select_related('thread', 'type') \
        .prefetch_related('update_set')

    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = len(Observation.objects.filter(date_closed__isnull=True))
        context['closed_count'] = len(Observation.objects.filter(date_closed__isnull=False))

        return context