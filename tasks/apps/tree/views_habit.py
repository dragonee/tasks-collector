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


@api_view(['GET'])
def my_habit_keywords(request):
    """Return the habit keywords filtered by the current user's profile

    Query parameters:
    - all=true: Return all habit keywords instead of just filtered ones

    If the user's profile has no keywords selected, returns all keywords.
    """
    from .models import HabitKeyword

    # Check if all keywords should be returned
    if request.query_params.get('all') == 'true':
        habit_keywords = HabitKeyword.objects.all()
        serializer = HabitKeywordSerializer(habit_keywords, many=True, context={'request': request})
        return RestResponse(serializer.data)

    # Return filtered keywords, or all if none selected
    try:
        profile = Profile.objects.get(user=request.user)
        habit_keywords = profile.habit_keywords.all()

        # If no keywords are selected, return all keywords
        if not habit_keywords.exists():
            habit_keywords = HabitKeyword.objects.all()

        serializer = HabitKeywordSerializer(habit_keywords, many=True, context={'request': request})
        return RestResponse(serializer.data)
    except Profile.DoesNotExist:
        # If no profile exists, return all keywords
        habit_keywords = HabitKeyword.objects.all()
        serializer = HabitKeywordSerializer(habit_keywords, many=True, context={'request': request})
        return RestResponse(serializer.data)
