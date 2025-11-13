from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from rest_framework import viewsets
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response as RestResponse
from rest_framework.pagination import PageNumberPagination

from django.views.generic.list import ListView
from django.views.generic.detail import DetailView

from django.db.models import Count, Q
from django.utils import timezone

from collections import Counter
from functools import cached_property

import datetime
from datetime import date

from .serializers import HabitSerializer, HabitKeywordSerializer
from .models import Habit, HabitTracked, Thread, Profile
from .forms import SingleHabitTrackedForm, OnlyTextSingleHabitTrackedForm

from .utils.itertools import itemize
from .utils.datetime import (
    adjust_start_date_to_monday,
    date_range_generator,
    DayCount,
)


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
            'total_event_count': self.tracked_habits.count(),
        })

        return context


class HabitListView(LoginRequiredMixin, ListView):
    model = Habit

def get_habit_keywords_for_user(user, all=False):
    from .models import HabitKeyword
    from django.db.models import Count

    def profile_has_keywords(user):
        return Profile.objects.annotate(
            keyword_count=Count('habit_keywords')
        ).filter(user=user, keyword_count__gt=0).exists()
   
    should_return_all_checks = [
        all,
        not profile_has_keywords(user),
    ]

    if any(should_return_all_checks):
        return HabitKeyword.objects.all()

    return Profile.objects.get(user=user).habit_keywords.all()


def get_habit_keywords_for_user_and_date(user, date, all=False):
    habit_keywords = get_habit_keywords_for_user(user, all=all)

    tracked_habit_ids = HabitTracked.objects.filter(
        published__date=date
    ).values_list('habit_id', flat=True).distinct()
    
    return habit_keywords.exclude(habit_id__in=tracked_habit_ids)

@api_view(['GET'])
def my_habit_keywords(request):
    """Return the habit keywords filtered by the current user's profile

    Query parameters:
    - all=true: Return all habit keywords instead of just filtered ones
    - date=YYYY-MM-DD: Filter out keywords for habits already tracked on this date (defaults to today)

    If the user's profile has no keywords selected, returns all keywords.
    If habits have been tracked on the specified date, their keywords are excluded.
    """
    import datetime

    # Parse date parameter (defaults to today)
    date_param = request.query_params.get('date')
    if date_param:
        try:
            target_date = datetime.datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            return RestResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)
    else:
        target_date = datetime.date.today()

    habit_keywords = get_habit_keywords_for_user_and_date(
        request.user, 
        target_date, 
        all=request.query_params.get('all') == 'true'
    )
    
    serializer = HabitKeywordSerializer(habit_keywords, many=True, context={'request': request})
    return RestResponse(serializer.data)
   
