from django.shortcuts import render, redirect

from rest_framework import viewsets
from rest_framework import status


from .serializers import *
from .models import *
from .forms import * 
from .commit import merge, calculate_changes_per_board
from .habits import habits_line_to_habits_tracked

from django.db.models import Count, Q
from datetime import date, timedelta

from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django_htmx.http import retarget, HttpResponseClientRefresh

from rest_framework.response import Response as RestResponse
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination

from django.utils import timezone
from django.shortcuts import get_object_or_404

from django.views.generic.list import ListView

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend

from django.db import transaction
from django.forms import inlineformset_factory

from django.urls import reverse

from django.views.generic.dates import ArchiveIndexView, MonthArchiveView, DayArchiveView, TodayArchiveView
from django.views.generic.detail import DetailView

from collections import Counter, namedtuple
from functools import cached_property

import datetime

from .utils.itertools import itemize

from .observation_operations import migrate_observation_updates_to_journal as _migrate_observation_updates_to_journal

class ObservationPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


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

def get_day_from_request(request):
    day = request.query_params.get('date')

    if day is not None:
        return datetime.datetime.strptime(day, '%Y-%m-%d').date()
    
    return date.today()

class HabitPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

class HabitViewSet(viewsets.ModelViewSet):
    serializer_class = HabitSerializer
    queryset = Habit.objects.all()

    pagination_class = HabitPagination

    def get_queryset(self):
        day = get_day_from_request(self.request)

        return super().get_queryset().annotate(
            today_tracked=Count(
                'habittracked',
                filter=Q(habittracked__published__date=day)
            ),
        )

class PlanFilter(filters.FilterSet):
    class Meta:
        model = Plan
        fields = {
            'pub_date': ('gte', 'lte', 'exact'),
        }

class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer

    filter_backends = [DjangoFilterBackend]
    filter_class = PlanFilter


class ReflectionViewSet(viewsets.ModelViewSet):
    queryset = Reflection.objects.all()
    serializer_class = ReflectionSerializer

class ObservationFilter(filters.FilterSet):
    class Meta:
        model = Observation
        fields = {
            'pub_date': ('gte', 'lte'),
            'event_stream_id': ('exact',)
        }

class EventFilter(filters.FilterSet):
    class Meta:
        model = Event
        fields = {
            'published': ('gte', 'lte'),
            'event_stream_id': ('exact',)
        }

class ObservationViewSet(viewsets.ModelViewSet):
    queryset = Observation.objects.all()

    filter_backends = [DjangoFilterBackend]
    filter_class = ObservationFilter

    pagination_class = ObservationPagination

    def get_serializer_class(self):
        features = self.request.query_params.get('features')

        if features and 'updates' in features:
            return ObservationWithUpdatesSerializer
        
        return ObservationSerializer

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


# XXX should we permit only POST here?
class JournalAddedViewSet(viewsets.ModelViewSet):
    queryset = JournalAdded.objects.all()
    serializer_class = JournalAddedSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        journal_added = serializer.save()

        add_reflection_items(journal_added)
        
        triplets = habits_line_to_habits_tracked(journal_added.comment)

        for occured, habit, note in triplets:
            HabitTracked.objects.create(
                occured=occured,
                habit=habit,
                note=note,
                published=journal_added.published,
                thread=Thread.objects.get(name='Daily'),
            )

class QuickNoteViewSet(viewsets.ModelViewSet):
    queryset = QuickNote.objects.order_by('published')
    serializer_class = QuickNoteSerializer

class ThreadViewSet(viewsets.ModelViewSet):
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

    return RestResponse(BoardSerializer(board).data)

@api_view(['POST'])
def add_task(request):
    item = request.data

    # XXX hackish
    if 'text' not in item or 'thread-name' not in item:
        return RestResponse({'errors': 'no thread-name and text'}, status=status.HTTP_400_BAD_REQUEST)
    
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

    return RestResponse(BoardSerializer(board).data)

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
        # Hack for django-debug-toolbar
        if attr == '_wrapped':
            raise AttributeError

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

DayCount = namedtuple('DayCount', ['date', 'count'])

def date_range_generator(start, end):
    current = start

    while current <= end:
        yield current.date()
        current += datetime.timedelta(days=1)


def _event_calendar(start, end):
    events = Event.objects.filter(
        published__range=(start, end),
    ).order_by('published').values('published')

    c = Counter()

    for event in events:
        c[event['published'].date()] += 1

    return c

def adjust_start_date_to_monday(date):
    if date.weekday() == 0:
        return date
    
    return date - datetime.timedelta(days=date.weekday())


def event_calendar(start, end):
    start = adjust_start_date_to_monday(start)

    return itemize(
        date_range_generator(start, end),
        _event_calendar(start, end),
        default=0,
        item_type=DayCount
    )

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
            save_or_remove_object_if_empty(today_plan, ['focus', 'want'])

        tomorrow_plan_form = PlanForm(request.POST, instance=tomorrow_plan, prefix="tomorrow_plan")
        tomorrow_valid = tomorrow_plan_form.is_valid()

        if tomorrow_valid:
            save_or_remove_object_if_empty(tomorrow_plan, ['focus', 'want'])

        reflection_form = ReflectionForm(request.POST, instance=reflection, prefix="reflection")
        reflection_valid = reflection_form.is_valid()

        if reflection_valid:
            save_or_remove_object_if_empty(reflection, ['good', 'better', 'best'])
            
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
        'event_calendar': event_calendar(day_start - datetime.timedelta(weeks=52), day_end),
    })

class ObservationListView(ListView):
    model = Observation
    queryset = Observation.objects \
        .select_related('thread', 'type') \
        .prefetch_related('observationupdated_set')

    paginate_by = 200

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = Observation.objects.count()
        context['closed_count'] = ObservationClosed.objects.count()

        return context

class ObservationClosedListView(ListView):
    model = ObservationClosed
    queryset = ObservationClosed.objects \
        .select_related('thread', 'type') \
        .order_by('-published')
    
    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['open_count'] = Observation.objects.count()
        context['closed_count'] = ObservationClosed.objects.count()

        return context

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
        initial_dict = {}

        if not observation.pub_date:
            initial_dict['pub_date'] = date.today()
        
        if not observation.type_id:
            initial_dict['type'] = ObservationType.objects.get(name='Observation')
        
        if not observation.thread_id:
            initial_dict['thread'] = Thread.objects.get(name='big-picture')

        form = ObservationForm(instance=observation, initial=initial_dict)
        formset = ObservationUpdatedFormSet(
            instance=observation,
            queryset=observation_updated_queryset,
        )
    
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
def track_habit(request):
    if request.GET.get('form') == 'only_text':
        form_class = OnlyTextSingleHabitTrackedForm
    else:
        form_class = SingleHabitTrackedForm

    form = form_class(request.data)

    if not form.is_valid():
        if request.htmx:
            return render(request, "tree/habit_tracked/form.html", {
                'form': form,
            })
        return RestResponse(form.errors, status=status.HTTP_400_BAD_REQUEST)
    
    habits_tracked = []

    for occured, habit, note in form.cleaned_data['triplets']:
        obj = HabitTracked.objects.create(
            occured=occured,
            habit=habit,
            note=note,
            published=form.cleaned_data['published'],
            thread=form.cleaned_data['thread'],
        )

        habits_tracked.append(obj)

    if request.htmx:
        initial_dict = {
        }

        if 'journal' in form.cleaned_data:
            initial_dict['journal'] = form.cleaned_data['journal']

        return render(request, "tree/habit_tracked/ok.html", {
            'habits_tracked': habits_tracked,
            'form': form_class(initial=initial_dict),
        })
    return RestResponse({'ok': True}, status=status.HTTP_200_OK)


@require_POST
def add_quick_note_hx(request):
    if not request.htmx:
        return HttpResponse("Only HTMX allowed", status=status.HTTP_400_BAD_REQUEST)

    form = QuickNoteForm(request.POST)

    if not form.is_valid():
        response = render(request, "tree/quick_note/form.html", {
            'form': form,
        })

        retarget(response, "#form")

        return response
    
    form.save()

    return HttpResponseClientRefresh()


def quick_notes(request):
    return render(request, "tree/quick_note.html", {
        'notes': QuickNote.objects.order_by('published'),
        'form': QuickNoteForm(),
    })


### XXX TODO 
### finish the editing views
### add auto-delete mechanism
class JournalArchiveContextMixin:
    def get_order(self):
        return self.request.GET.get('order', 'desc')

    def get_queryset(self):
        queryset = super().get_queryset()

        return queryset.order_by(
            'published' if self.get_order() == 'asc' else '-published'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['order'] = self.get_order()
        context['dates'] = self.get_queryset().dates(
            'published', 
            'month', 
            order='DESC'
        )
        context['tags'] = JournalTag.objects.all()

        return context

class EventArchiveContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dates'] = Event.objects.dates(
            'published', 
            'month', 
            order='DESC'
        )
        return context

class CurrentMonthArchiveView(MonthArchiveView):
    def get_month(self):
        return timezone.now().month

    def get_year(self):
        return timezone.now().year
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_current_month'] = True
        return context


class JournalCurrentMonthArchiveView(JournalArchiveContextMixin, CurrentMonthArchiveView):
    model = JournalAdded
    date_field = 'published'
    allow_future = True
    allow_empty = True
    

    template_name = 'tree/journaladded_archive_month.html'


class JournalArchiveMonthView(JournalArchiveContextMixin, MonthArchiveView):
    model = JournalAdded
    date_field = 'published'
    allow_future = True


class JournalTagArchiveContextMixin(JournalArchiveContextMixin):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['tag'] = JournalTag.objects.get(slug=self.kwargs['slug'])

        return context

class JournalTagArchiveMonthView(JournalTagArchiveContextMixin, MonthArchiveView):
    model = JournalAdded
    date_field = 'published'
    allow_future = True

    def get_queryset(self):
        return super().get_queryset().filter(tags__slug=self.kwargs['slug'])
    
    template_name = 'tree/journaladded_archive_month.html'


class JournalTagCurrentMonthArchiveView(JournalTagArchiveContextMixin, CurrentMonthArchiveView):
    model = JournalAdded
    date_field = 'published'
    allow_future = True

    def get_queryset(self):
        return super().get_queryset().filter(tags__slug=self.kwargs['slug'])
    
    template_name = 'tree/journaladded_archive_month.html'

class EventCurrentMonthArchiveView(EventArchiveContextMixin, CurrentMonthArchiveView):
    model = Event
    date_field = 'published'
    allow_future = True

class EventArchiveMonthView(EventArchiveContextMixin, MonthArchiveView):
    model = Event
    date_field = 'published'
    allow_future = True


def _habit_calendar(habit, start, end):
    events = HabitTracked.objects.filter(
        habit=habit,
        published__range=(start, end),
    ).order_by('published').values('published', 'occured')

    c = Counter()

    for event in events:
        if c[event['published'].date()] == -1:
            continue

        if event['occured'] == False:
            c[event['published'].date()] = -1
            continue

        c[event['published'].date()] += 1

    return c


def habit_calendar(habit, start, end):
    start = adjust_start_date_to_monday(start)

    return itemize(
        date_range_generator(start, end),
        _habit_calendar(habit, start, end),
        default=0,
        item_type=DayCount
    )

class HabitDetailView(DetailView):
    model = Habit

    def get_slug_field(self) -> str:
        return 'slug'
    
    @cached_property
    def tracked_habits(self):
        return HabitTracked.objects.filter(habit=self.object).order_by('-published')

    def get_context_data(self, **kwargs):
        start = timezone.now() - datetime.timedelta(days=365)
        end = timezone.now() + datetime.timedelta(days=1)

        context = super().get_context_data(**kwargs)

        context.update({
            'event_calendar': habit_calendar(self.object, start, end),
            'tracked_habits': self.tracked_habits,
        })

        return context

class HabitListView(ListView):
    model = Habit



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

def breakthrough(request, year):
    year = int(year)
    last_year = year - 1

    try:
        breakthrough = Breakthrough.objects.get(slug=f'{year}')
    except Breakthrough.DoesNotExist:
        breakthrough = Breakthrough(slug=f'{year}')

    ProjectedOutcomeFormSet = inlineformset_factory(Breakthrough, ProjectedOutcome, form=ProjectedOutcomeForm, extra=1)
    projected_outcome_queryset = ProjectedOutcome.objects.filter(breakthrough=breakthrough).order_by('resolved_by')

    if request.method == 'POST':
        form = BreakthroughForm(request.POST, instance=breakthrough)
        formset = ProjectedOutcomeFormSet(
            request.POST,
            instance=breakthrough,
            queryset=projected_outcome_queryset,
        )

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()

            return redirect(reverse('breakthrough', args=[year]))
    else:
        form = BreakthroughForm(instance=breakthrough)
        formset = ProjectedOutcomeFormSet(
            instance=breakthrough,
            queryset=projected_outcome_queryset,
        )
    
    breakthrough_habits = HabitTracked.objects.filter(
        published__year=last_year,
        habit__slug='breakthrough',
    ).select_related('habit')

    return render(request, "tree/breakthrough.html", {
        'year': year,
        'breakthrough_habits': breakthrough_habits,
        'form': form,
        'formset': formset,
        'projected_outcome_queryset': projected_outcome_queryset,
    })

def stats(request):
    journal_qs = JournalAdded.objects.all()
    habit_qs = HabitTracked.objects.all()
    observation_qs = ObservationMade.objects.all()
    observation_updated_qs = ObservationUpdated.objects.all()
    observation_closed_qs = ObservationClosed.objects.all()
    event_qs = Event.objects.all()
    observation_recontextualized_qs = ObservationRecontextualized.objects.all()
    observation_reflected_upon_qs = ObservationReflectedUpon.objects.all()
    observation_reinterpreted_qs = ObservationReinterpreted.objects.all()

    try:
        year = int(request.GET.get('year'))
    except (ValueError, TypeError):
        year = None

    if year:
        journal_qs = journal_qs.filter(published__year=year)
        habit_qs = habit_qs.filter(published__year=year)
        observation_qs = observation_qs.filter(published__year=year)
        observation_updated_qs = observation_updated_qs.filter(published__year=year)
        observation_closed_qs = observation_closed_qs.filter(published__year=year)
        event_qs = event_qs.filter(published__year=year)
        observation_recontextualized_qs = observation_recontextualized_qs.filter(published__year=year)
        observation_reflected_upon_qs = observation_reflected_upon_qs.filter(published__year=year)
        observation_reinterpreted_qs = observation_reinterpreted_qs.filter(published__year=year)

    return render(request, "tree/stats.html", {
        'year': year,
        'years': range(timezone.now().year, 2018, -1),
        'journal_count': journal_qs.count(),
        'habit_count': habit_qs.count(),
        'observation_count': observation_qs.count(),
        'observation_updated_count': observation_updated_qs.count(),
        'observation_closed_count': observation_closed_qs.count(),
        'event_count': event_qs.count(),
        'observation_recontextualized_count': observation_recontextualized_qs.count(),
        'observation_reflected_upon_count': observation_reflected_upon_qs.count(),
        'observation_reinterpreted_count': observation_reinterpreted_qs.count(),
    })
