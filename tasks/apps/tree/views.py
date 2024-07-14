from django.shortcuts import render, redirect

from rest_framework import viewsets
from rest_framework import status


from .serializers import BoardSerializer, BoardSummary, ThreadSerializer, PlanSerializer, ReflectionSerializer, ObservationSerializer, ObservationUpdatedSerializer, spawn_observation_events, JournalAddedSerializer
from .models import Event, Board, JournalAdded, Thread, Plan, Reflection, Observation, ObservationType, BoardCommitted, default_state, Habit, HabitTracked, ObservationUpdated, ObservationMade, ObservationClosed, ObservationRecontextualized, ObservationReflectedUpon, ObservationReinterpreted
from .forms import PlanForm, ReflectionForm, ObservationForm
from .commit import merge, calculate_changes_per_board
from .habits import habits_line_to_habits_tracked

from datetime import date

from rest_framework.response import Response
from rest_framework.decorators import api_view

from django.utils import timezone
from django.shortcuts import get_object_or_404

from django.views.generic.list import ListView

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend

from django.db import transaction
from django.forms import inlineformset_factory

from django.urls import reverse

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

class ObservationUpdatedViewSet(viewsets.ModelViewSet):
    queryset = ObservationUpdated.objects.all()
    serializer_class = ObservationUpdatedSerializer


# XXX should we permit only POST here?
class JournalAddedViewSet(viewsets.ModelViewSet):
    queryset = JournalAdded.objects.all()
    serializer_class = JournalAddedSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        journal_added = serializer.save()
        triplets = habits_line_to_habits_tracked(journal_added.comment)

        for occured, habit, note in triplets:
            HabitTracked.objects.create(
                occured=occured,
                habit=habit,
                note=note,
                published=timezone.now(),
                thread=Thread.objects.get(name='Daily'),
            )

class ThreadViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """
    queryset = Thread.objects.all()
    serializer_class = ThreadSerializer

def make_board(thread_name):
    thread=Thread.objects.get(name=thread_name)

    try:
        return Board.objects.filter(thread=thread)[0]
    except IndexError:
        return Board(thread=thread)


@api_view(['POST'])
def commit_board(request, id=None):
    board = Board.objects.get(pk=id)

    changeset = calculate_changes_per_board(board.state)

    # for name, changes in changeset.items():
    #     print("Board ({})".format(name))
    #     pprint(changes)
    #     print('------------------', flush=True)

    if None in changeset:
        new_state = changeset[None]
        del changeset[None]
    else:
        new_state = default_state()

    now = timezone.now()

    BoardCommitted.objects.create(
        published=now,
        thread=board.thread,
        focus=board.focus or '',
        before=board.state,
        after=new_state,
        transitions=changeset,
        date_started=board.date_started,
    )

    other_boards = list(map(make_board, changeset.keys()))

    for other_board in other_boards:
        other_board.state = merge(other_board.state, changeset[other_board.thread.name])    
        other_board.save()

    board.state = new_state
    board.date_started = now
    board.save()

    return Response(BoardSerializer(board).data)

@api_view(['POST'])
def add_task(request):
    item = request.data

    # XXX hackish
    if 'text' not in item or 'thread-name' not in item:
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
    board = get_object_or_404(BoardCommitted, pk=id)

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

    boards = BoardCommitted.objects.filter(published__range=period).order_by('-published')

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
        now = timezone.make_aware(datetime.datetime.strptime(request.GET['date'], '%Y-%m-%d'))
        today = now.date()
    except KeyError:
        now = timezone.now()

        today = now.date()

        if 0 <= now.hour < 12:
            today -= datetime.timedelta(days=1)

    day_start = timezone.make_aware(datetime.datetime.combine(today, datetime.datetime.min.time()))
    day_end = timezone.make_aware(datetime.datetime.combine(today, datetime.datetime.max.time()))

    if not day_start <= now <= day_end:
        now = day_end

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

    habits = Habit.objects.all()
    tracked_habits = HabitTracked.objects.filter(
         published__range=(day_start, day_end)
    )
  
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

    journals = JournalAdded.objects.filter(
        published__gte=today - datetime.timedelta(days=1),
    ).order_by('published')

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

        'habits': habits,
        'tracked_habits': tracked_habits,

        'thread': thread,
        'threads': Thread.objects.all(),

        'journals': journals,
    })

class ObservationListView(ListView):
    model = Observation
    queryset = Observation.objects \
        .filter(date_closed__isnull=True) \
        .select_related('thread', 'type') \
        .prefetch_related('observationupdated_set')

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
        .prefetch_related('observationupdated_set')

    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = len(Observation.objects.filter(date_closed__isnull=True))
        context['closed_count'] = len(Observation.objects.filter(date_closed__isnull=False))

        return context


def observation_edit(request, observation_id=None):
    if observation_id is not None:
        observation = get_object_or_404(Observation, id=observation_id)        
    else:
        observation = Observation()

    previous = observation.copy(as_new=False)

    # XXX TODO add ability to set events on a specific day... OR NOT
    # We can actually add the date attribute to an event
    # And because of that we can still set published date always to the current date
    # And leave out affected

    ObservationUpdatedFormSet = inlineformset_factory(Observation, ObservationUpdated, fields=('comment',), extra=3)

    if request.method == "POST":
        form = ObservationForm(request.POST, instance=observation)
        formset = ObservationUpdatedFormSet(request.POST, instance=observation)

        now = timezone.now()

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.save()
                
                events = spawn_observation_events(previous, obj, published=now)
                for event in events:
                    event.save()

                updates = formset.save(commit=False)
                for update in updates:
                    update.published = now
                    update.save()

            return redirect(reverse('public-observation-list'))

    else:
        initial_dict = {}

        if not observation.pub_date:
            initial_dict['pub_date'] = date.today()
        
        if not observation.type_id:
            initial_dict['type'] = ObservationType.objects.first()
        
        if not observation.thread_id:
            initial_dict['thread'] = Thread.objects.get(name='big-picture')

        form = ObservationForm(instance=observation, initial=initial_dict)
        formset = ObservationUpdatedFormSet(instance=observation)
    
    if observation.event_stream_id:
        events = Event.objects.filter(event_stream_id=observation.event_stream_id)
    else:
        events = []

    return render(request, "tree/observation_edit.html", {
        "events": events,
        "form": form,
        "formset": formset,
        "instance": observation,
        "thread_as_link": True,
    })