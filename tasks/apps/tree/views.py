from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from rest_framework import viewsets
from rest_framework import status


from .serializers import *
from .models import *
from .forms import * 
from .commit import merge, calculate_changes_per_board
from .habits import habits_line_to_habits_tracked

from django.db.models import Count, Q, Exists, OuterRef
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
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

from django.contrib import messages

from django.urls import reverse

from django.views.generic.dates import ArchiveIndexView, MonthArchiveView, DayArchiveView, TodayArchiveView
from django.views.generic.detail import DetailView

from collections import Counter, namedtuple
from functools import cached_property
from calendar import monthrange

import datetime

from .utils.itertools import itemize

from .observation_operations import migrate_observation_updates_to_journal as _migrate_observation_updates_to_journal
from .utils.statistics import get_word_count_statistic
from .presenters import ComplexPresenter

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
    thread = filters.CharFilter(field_name='thread__name')
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

        # Handle reflect command
        if 'reflection' in self.request.data:
            return
        
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

class ProfileViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProfileSerializer
    
    def get_queryset(self):
        # Only return the current user's profile
        return Profile.objects.filter(user=self.request.user)

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

def _get_current_plans():
    """Helper function to get current Daily, Weekly, and big-picture plans"""
    from datetime import date
    
    today = date.today()
    
    try:
        daily_plan = Plan.objects.get(pub_date=today, thread__name='Daily')
    except Plan.DoesNotExist:
        daily_plan = None
        
    try:
        weekly_plan = Plan.objects.get(pub_date=make_last_day_of_the_week(today), thread__name='Weekly')
    except Plan.DoesNotExist:
        weekly_plan = None
        
    try:
        big_picture_plan = Plan.objects.get(pub_date=make_last_day_of_the_month(today), thread__name='big-picture')
    except Plan.DoesNotExist:
        big_picture_plan = None
    
    return {
        'daily_plan': daily_plan,
        'weekly_plan': weekly_plan,
        'big_picture_plan': big_picture_plan,
    }

def _add_task_to_board(text, thread_name):
    """Helper function to add a task to a board"""
    thread = get_object_or_404(Thread, name=thread_name)
    board = Board.objects.filter(thread=thread).order_by('-date_started').first()
    if board:
        board.state.append({
            'children': [],
            'data': {
                'state': 'open',
                'text': text,
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
            'text': text,
        })
        board.save()
        return board
    return None

@api_view(['POST'])
def add_task(request):
    item = request.data

    # XXX hackish
    if 'text' not in item or 'thread-name' not in item:
        return RestResponse({'errors': 'no thread-name and text'}, status=status.HTTP_400_BAD_REQUEST)
    
    board = _add_task_to_board(item['text'], item['thread-name'])
    return RestResponse(BoardSerializer(board).data)

@login_required
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

@login_required
def summaries(request):
    period = period_from_request(request, days=30)

    boards = BoardCommitted.objects.filter(published__range=period).order_by('-published')

    summaries = [BoardSummary(board) for board in boards]

    return render(request, 'summary.html', {
        'boards': boards,
        'summaries': summaries,
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


def adjust_date_to_sunday(date):
    """Adjust date to the Sunday of its week (6 = Sunday in Python's weekday system)"""
    days_until_sunday = (6 - date.weekday()) % 7
    return date + datetime.timedelta(days=days_until_sunday)


def get_week_period(date):
    """Get the (start, end) tuple for the week containing the given date"""
    monday = adjust_start_date_to_monday(date)
    sunday = monday + datetime.timedelta(days=6)
    return (monday, sunday)


def get_month_period(date):
    """Get the (start, end) tuple for the month containing the given date"""
    month_start = date.replace(day=1)
    month_end = date.replace(day=monthrange(date.year, date.month)[1])
    return (month_start, month_end)


def generate_periods(start, end, period_func):
    """Generate all periods between start and end using the given period function"""
    periods = []
    seen_periods = set()

    current = start
    while current <= end:
        period = period_func(current)
        if period not in seen_periods:
            periods.append(period)
            seen_periods.add(period)

        # Move forward by the period duration
        if period_func == get_week_period:
            current += datetime.timedelta(days=7)
        else:  # monthly
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    return periods


def get_summary_calendar(start, end, thread_name, period_func):
    """Generic function to get summary calendar for any period type"""
    # Get all reflections for this thread
    reflections = Reflection.objects.filter(
        pub_date__range=(start, end),
        thread__name=thread_name
    ).values('pub_date')

    # Group reflections by their periods
    periods_with_summaries = Counter()
    for reflection in reflections:
        period = period_func(reflection['pub_date'])
        periods_with_summaries[period] += 1

    # Generate all periods in the date range
    all_periods = generate_periods(start, end, period_func)

    # Create result list with period end dates and counts
    result = []
    for period_start, period_end in all_periods:
        period_tuple = (period_start, period_end)
        count = periods_with_summaries.get(period_tuple, 0)
        has_summary = 1 if count > 0 else 0
        result.append(DayCount(date=period_end, count=has_summary))

    return result


def event_calendar(start, end):
    start = adjust_start_date_to_monday(start)

    return itemize(
        date_range_generator(start, end),
        _event_calendar(start, end),
        default=0,
        item_type=DayCount
    )


def weekly_summary_calendar(start, end):
    """Generate calendar data for weekly summaries - one indicator per week"""
    start = adjust_start_date_to_monday(start)
    return get_summary_calendar(start, end, 'Weekly', get_week_period)


def monthly_summary_calendar(start, end):
    """Generate calendar data for monthly summaries - mark ALL weeks within months that have summaries"""
    start = adjust_start_date_to_monday(start)

    # Get monthly reflections
    reflections = Reflection.objects.filter(
        pub_date__range=(start, end),
        thread__name='big-picture'
    ).values('pub_date')

    # Map monthly summaries to months
    months_with_summaries = set()
    for reflection in reflections:
        month_key = (reflection['pub_date'].year, reflection['pub_date'].month)
        months_with_summaries.add(month_key)

    # Generate all weekly periods in the date range
    all_weekly_periods = generate_periods(start, end, get_week_period)

    # Create result list - mark ALL weeks that fall within months with summaries
    result = []
    for period_start, period_end in all_weekly_periods:
        # Check if any day in this week falls within a month that has a summary
        has_summary = 0

        # Check each day in this week
        current_day = period_start
        while current_day <= period_end:
            month_key = (current_day.year, current_day.month)
            if month_key in months_with_summaries:
                has_summary = 1
                break
            current_day += datetime.timedelta(days=1)

        result.append(DayCount(date=period_end, count=has_summary))

    return result


def make_last_day_of_the_week(date):
    return date + datetime.timedelta(days=(6 - date.weekday()))

def make_last_day_of_the_month(date):
    return date.replace(day=monthrange(date.year, date.month)[1])

@login_required
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

    if thread.name == 'Weekly':
        other_day = make_last_day_of_the_week(today)
        if other_day != today:
            return redirect(reverse('public-today') + '?date={}&thread={}'.format(other_day, thread.name))

    if thread.name == 'big-picture':
        other_day = today.replace(day=monthrange(today.year, today.month)[1])
        if other_day != today:
            return redirect(reverse('public-today') + '?date={}&thread={}'.format(other_day, thread.name))

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
        thread=thread,
    ).order_by('published')

    def get_last_date(date, thread):
        if thread.name == 'Weekly':
            return make_last_day_of_the_week(date - datetime.timedelta(days=7))
        elif thread.name == 'big-picture':
            return date.replace(day=1) - datetime.timedelta(days=1)

        return date - datetime.timedelta(days=1)

    def get_next_date(date, thread):
        if thread.name == 'Weekly':
            return make_last_day_of_the_week(date + datetime.timedelta(days=7))
        elif thread.name == 'big-picture':
            next_month = date.replace(day=28) + datetime.timedelta(days=4)
            return make_last_day_of_the_month(next_month)

        return date + datetime.timedelta(days=1)

    def get_larger_plan(date):
        try:
            if thread.name == 'Weekly':
                return Plan.objects.get(pub_date=make_last_day_of_the_month(date), thread__name='big-picture')
            
            return Plan.objects.get(pub_date=make_last_day_of_the_week(date), thread__name='Weekly')
        except Plan.DoesNotExist:
            return None

    return render(request, 'today.html', {
        'yesterday': get_last_date(today, thread),
        'today': today,
        'actual_today': timezone.now().date(),
        'is_today': today == timezone.now().date(),
        'tomorrow': get_next_date(today, thread),
        'today_plan': today_plan,
        'tomorrow_plan': tomorrow_plan,
        'reflection': reflection,
        'larger_plan': get_larger_plan(today),

        'today_plan_form': today_plan_form,
        'tomorrow_plan_form': tomorrow_plan_form,
        'reflection_form': reflection_form,

        'habits': habits,
        'tracked_habits': tracked_habits,

        'thread': thread,
        'threads': Thread.objects.all(),

        'journals': journals,
        'event_calendar': event_calendar(day_start - datetime.timedelta(weeks=52), day_end),
        'weekly_summary_calendar': weekly_summary_calendar((day_start - datetime.timedelta(weeks=52)).date(), day_end.date()),
        'monthly_summary_calendar': monthly_summary_calendar((day_start - datetime.timedelta(weeks=52)).date(), day_end.date()),
    })

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

@login_required
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
        # Initialize ComplexPresenter for this observation
        complex_presenter = ComplexPresenter(observation.event_stream_id)
    else:
        events = []
        complex_presenter = None

    return render(request, "tree/observation_edit.html", {
        "events": events,
        "form": form,
        "formset": formset,
        "instance": observation,
        "thread_as_link": True,
        "complex_presenter": complex_presenter,
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
@login_required
def add_quick_note_hx(request):
    if not request.htmx:
        return HttpResponse("Only HTMX allowed", status=status.HTTP_400_BAD_REQUEST)

    form = QuickContentForm(request.POST)

    if not form.is_valid():
        response = render(request, "tree/quick_note/form.html", {
            'form': form,
        })

        retarget(response, "#form")

        return response
    
    content_type = form.cleaned_data['content_type']
    content = form.cleaned_data['content']
    
    if content_type == 'quick_note':
        QuickNote.objects.create(note=content)
    elif content_type == 'task':
        # Add task to current inbox board
        _add_task_to_board(content, 'Inbox')
    elif content_type == 'plan_focus':
        timeframe = form.cleaned_data['focus_timeframe']
        from datetime import date, timedelta
        
        if timeframe == 'today':
            focus_date = date.today()
            thread = Thread.objects.get(name='Daily')
        elif timeframe == 'tomorrow':
            focus_date = date.today() + timedelta(days=1)
            thread = Thread.objects.get(name='Daily')
        elif timeframe == 'this_week':
            focus_date = date.today()
            thread = Thread.objects.get(name='Weekly')
        
        plan, created = Plan.objects.get_or_create(
            pub_date=focus_date,
            thread=thread,
            defaults={'focus': content}
        )
        if not created:
            # Append to existing focus content
            if plan.focus:
                plan.focus += '\n' + content
            else:
                plan.focus = content
            plan.save()

    return HttpResponseClientRefresh()


@login_required
def quick_notes(request):
    context = {
        'notes': QuickNote.objects.order_by('published'),
        'form': QuickContentForm(),
    }
    context.update(_get_current_plans())
    
    return render(request, "tree/quick_note.html", context)


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

class CurrentMonthArchiveView(LoginRequiredMixin, MonthArchiveView):
    allow_empty = True

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

    template_name = 'tree/journaladded_archive_month.html'


class JournalArchiveMonthView(LoginRequiredMixin, JournalArchiveContextMixin, MonthArchiveView):
    model = JournalAdded
    date_field = 'published'
    allow_future = True


class JournalTagArchiveContextMixin(JournalArchiveContextMixin):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['tag'] = JournalTag.objects.get(slug=self.kwargs['slug'])

        return context

class JournalTagArchiveMonthView(LoginRequiredMixin, JournalTagArchiveContextMixin, MonthArchiveView):
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

class EventArchiveMonthView(LoginRequiredMixin, EventArchiveContextMixin, MonthArchiveView):
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

class HabitDetailView(LoginRequiredMixin, DetailView):
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

class HabitListView(LoginRequiredMixin, ListView):
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

@login_required
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


@login_required
def projected_outcome_events_history(request, event_stream_id):
    """Display the event history for a specific ProjectedOutcome by event_stream_id"""
    from .presentation import ProjectedOutcomePresentation
    
    # Create a presentation object that handles both active and complete scenarios
    presentation = ProjectedOutcomePresentation.from_event_stream_id(event_stream_id)
    
    return render(request, "tree/projected_outcome_events_history.html", {
        'presentation': presentation,
        # Legacy context for backwards compatibility (can be removed once template is updated)
        'projected_outcome': presentation.active_instance,
        'latest_closed_event': presentation.closed_events[-1] if presentation.closed_events else None,
        'all_events': presentation.events,
        'made_events': presentation.made_events,
        'redefined_events': presentation.redefined_events,
        'rescheduled_events': presentation.rescheduled_events,
        'closed_events': presentation.closed_events,
    })

@login_required
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
    projected_outcome_made_qs = ProjectedOutcomeMade.objects.all()
    projected_outcome_redefined_qs = ProjectedOutcomeRedefined.objects.all()
    projected_outcome_rescheduled_qs = ProjectedOutcomeRescheduled.objects.all()
    projected_outcome_closed_qs = ProjectedOutcomeClosed.objects.all()

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
        projected_outcome_made_qs = projected_outcome_made_qs.filter(published__year=year)
        projected_outcome_redefined_qs = projected_outcome_redefined_qs.filter(published__year=year)
        projected_outcome_rescheduled_qs = projected_outcome_rescheduled_qs.filter(published__year=year)
        projected_outcome_closed_qs = projected_outcome_closed_qs.filter(published__year=year)

    # Get word count statistic
    word_count, word_count_updated = get_word_count_statistic(year=year)

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
        'projected_outcome_made_count': projected_outcome_made_qs.count(),
        'projected_outcome_redefined_count': projected_outcome_redefined_qs.count(),
        'projected_outcome_rescheduled_count': projected_outcome_rescheduled_qs.count(),
        'projected_outcome_closed_count': projected_outcome_closed_qs.count(),
        'word_count': word_count,
        'word_count_updated': word_count_updated,
    })

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
        observations = Observation.objects.extra(
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
    observations = Observation.objects.annotate(
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


@api_view(['GET'])
def daily_events(request):
    day = request.GET.get('date', timezone.now().date())

    thread_name = request.GET.get('thread', 'Daily')

    events = Event.objects.filter(published__date=day, thread__name=thread_name).not_instance_of(BoardCommitted)

    try:
        plan = Plan.objects.get(pub_date=day, thread__name=thread_name)
    except Plan.DoesNotExist:
        plan = None

    try:
        reflection = Reflection.objects.get(pub_date=day, thread__name=thread_name)
    except Reflection.DoesNotExist:
        reflection = None

    return RestResponse({
        'date': day,
        'events': EventSerializer(events, many=True, context={'request': request}).data,
        'plan': PlanSerializer(plan, context={'request': request}).data if plan else None,
        'reflection': ReflectionSerializer(reflection, context={'request': request}).data if reflection else None,
    })

@login_required
def account_settings(request):
    try:
        profile = Profile.objects.get(user=request.user)
    except Profile.DoesNotExist:
        profile = Profile(user=request.user)

    if request.method == 'POST':
        profile_form = ProfileForm(request.POST, instance=profile)
        user_form = UserForm(request.POST, instance=request.user)
        if profile_form.is_valid() and user_form.is_valid():
            profile_form.save()
            user_form.save()
            messages.success(request, 'Settings saved successfully!')
            return redirect('account-settings')
    else:
        profile_form = ProfileForm(instance=profile)
        user_form = UserForm(instance=request.user)

    return render(request, 'tree/account_settings.html', {
        'profile_form': profile_form,
        'user_form': user_form,
        'profile': profile,
    })

@login_required
def todo(request):
    try:
        profile = Profile.objects.get(user=request.user)
    except Profile.DoesNotExist:
        profile = None
    
    return render(request, 'tree/tasks.html', {
        'profile': profile,
    })
