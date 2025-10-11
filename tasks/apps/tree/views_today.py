from re import A
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import Plan, Reflection, Habit, HabitTracked, JournalAdded, Thread, Event
from .forms import PlanForm, ReflectionForm

from collections import Counter
from abc import ABC, abstractmethod

import datetime
from datetime import date

from .utils.itertools import itemize
from .utils.datetime import (
    DayCount,
    date_range_generator,
    adjust_start_date_to_monday,
    make_last_day_of_the_week,
    make_last_day_of_the_month,
    get_week_period,
    generate_periods,
)

from django.urls import reverse


def make_aware_start(date):
    """Convert a date to timezone-aware datetime at the start of the day"""
    return timezone.make_aware(datetime.datetime.combine(date, datetime.datetime.min.time()))


def make_aware_end(date):
    """Convert a date to timezone-aware datetime at the end of the day"""
    return timezone.make_aware(datetime.datetime.combine(date, datetime.datetime.max.time()))


class Period(ABC):
    """Base class for time periods (Daily, Weekly, Monthly)"""

    def __init__(self, date):
        """
        Initialize period with a date.

        Args:
            date: datetime.date object representing any date within the period
        """
        self.date = date if isinstance(date, datetime.date) else date.date()
        self._start = None
        self._end = None

    @property
    def start(self):
        """Get the start date of the period"""
        if self._start is None:
            self._start = self._calculate_start()
        return self._start

    @property
    def end(self):
        """Get the end date of the period"""
        if self._end is None:
            self._end = self._calculate_end()
        return self._end
    
    def as_tuple(self):
        """Get the start and end dates of the period as a tuple"""
        return (self.start, self.end)

    @abstractmethod
    def _calculate_start(self):
        """Calculate the start date of the period"""
        pass

    @abstractmethod
    def _calculate_end(self):
        """Calculate the end date of the period"""
        pass

    @abstractmethod
    def get_canonical_date(self):
        """Get the canonical date for this period (typically the end date)"""
        pass

    def is_canonical(self):
        """Check if the current date is the canonical date for this period"""
        return self.date == self.get_canonical_date()

    def canonical(self):
        """Return a new Period instance with the canonical date"""
        return self.__class__(self.get_canonical_date())

    @abstractmethod
    def get_previous(self):
        """Get the previous period (as canonical)"""
        pass

    @abstractmethod
    def get_next(self):
        """Get the next period (as canonical)"""
        pass

    def __eq__(self, other):
        """Check equality based on start and end dates"""
        if not isinstance(other, Period):
            return False
        return self.start == other.start and self.end == other.end

    def __hash__(self):
        """Make Period hashable for use in sets and dicts"""
        return hash((self.start, self.end))

    def __repr__(self):
        """String representation of the period"""
        return f"{self.__class__.__name__}({self.date}) [{self.start} to {self.end}]"


class Daily(Period):
    """Represents a single day period"""

    def _calculate_start(self):
        return make_aware_start(self.date)

    def _calculate_end(self):
        return make_aware_end(self.date)

    def get_canonical_date(self):
        """For daily periods, the date itself is canonical"""
        return self.date

    def get_previous(self):
        """Get the previous day"""
        return Daily(self.date - datetime.timedelta(days=1))

    def get_next(self):
        """Get the next day"""
        return Daily(self.date + datetime.timedelta(days=1))


class Weekly(Period):
    """Represents a week period (Monday to Sunday)"""

    def _calculate_start(self):
        """Start of week is Monday"""
        start_date = adjust_start_date_to_monday(self.date)
        return make_aware_start(start_date)

    def _calculate_end(self):
        """End of week is Sunday"""
        end_date = make_last_day_of_the_week(self.date)
        return make_aware_end(end_date)

    def get_canonical_date(self):
        """Canonical date for weekly periods is Sunday (end of week)"""
        return make_last_day_of_the_week(self.date)

    def get_previous(self):
        """Get the previous week (canonical = Sunday)"""
        prev_week_date = adjust_start_date_to_monday(self.date) - datetime.timedelta(days=7)
        return Weekly(prev_week_date).canonical()

    def get_next(self):
        """Get the next week (canonical = Sunday)"""
        next_week_date = make_last_day_of_the_week(self.date) + datetime.timedelta(days=1)
        return Weekly(next_week_date).canonical()


class Monthly(Period):
    """Represents a month period"""

    def _calculate_start(self):
        """Start of month is the first day"""
        start_date = self.date.replace(day=1)
        return make_aware_start(start_date)

    def _calculate_end(self):
        """End of month is the last day"""
        end_date = make_last_day_of_the_month(self.date)
        return make_aware_end(end_date)

    def get_canonical_date(self):
        """Canonical date for monthly periods is the last day of the month"""
        return make_last_day_of_the_month(self.date)

    def get_previous(self):
        """Get the previous month (canonical = last day of previous month)"""
        # Go to the first day of current month, then back one day
        first_of_month = self.date.replace(day=1)
        prev_month_end = first_of_month - datetime.timedelta(days=1)
        return Monthly(prev_month_end).canonical()

    def get_next(self):
        """Get the next month (canonical = last day of next month)"""
        # Go to the last day of current month, then forward one day
        last_of_month = make_last_day_of_the_month(self.date)
        next_month_start = last_of_month + datetime.timedelta(days=1)
        return Monthly(next_month_start).canonical()


def _event_calendar(start, end):
    events = Event.objects.filter(
        published__range=(start, end),
    ).order_by('published').values('published')

    c = Counter()

    for event in events:
        c[event['published'].date()] += 1

    return c


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


def save_or_remove_object_if_empty(object, fields):
    is_empty = not any(getattr(object, field) for field in fields)

    if not is_empty:
        object.save()
    elif object.pk:
        object.delete()


def validate_form_and_perform_save_or_delete(form, fields):
    is_valid = form.is_valid()
    
    if is_valid:
        save_or_remove_object_if_empty(form.instance, fields)
    
    return is_valid, form


def is_before_noon():
    return timezone.now().hour < 12


def yesterday(date):
    return date - datetime.timedelta(days=1)


def get_period_by_thread(thread):
    if thread.name == 'Weekly':
        return Weekly
    elif thread.name == 'big-picture':
        return Monthly
    else:
        return Daily


def get_larger_plan(period, thread):
    mapping = {
        'Weekly': ('big-picture', Monthly),
        'Daily': ('Weekly', Weekly),
    }

    try:
        larger_thread, larger_period_cls = mapping[thread.name]
    except KeyError:
        return None

    larger_period = larger_period_cls(period.get_canonical_date())

    try:
        return Plan.objects.get(pub_date=larger_period.get_canonical_date(), thread__name=larger_thread)
    except Plan.DoesNotExist:
        return None


def get_larger_plans(period, thread):
    plans = []
    
    larger_plan = get_larger_plan(period, thread)
    while larger_plan:
        plans.append(larger_plan)
        period = get_period_by_thread(larger_plan.thread)(larger_plan.pub_date)
        larger_plan = get_larger_plan(period, larger_plan.thread)
    
    return plans


def get_period_from_request(request, thread):
    """Extract date from request and create appropriate period instance"""
    try:
        today = date.fromisoformat(request.GET['date'])
    except (KeyError, ValueError):
        today = yesterday(date.today()) if is_before_noon() else date.today()

    period_cls = get_period_by_thread(thread)
    return period_cls(today)


def get_or_initial(model_class, **kwargs):
    """Get existing object or create new one with given kwargs"""
    try:
        return model_class.objects.get(**kwargs)
    except model_class.DoesNotExist:
        return model_class(**kwargs)


@login_required
def today(request):
    if request.method == 'POST':
        thread_name = request.POST.get('thread')
    else:
        thread_name = request.GET.get('thread', 'Daily')

    thread = Thread.objects.get(name=thread_name)
    
    period = get_period_from_request(request, thread)

    if not period.is_canonical():
        return redirect(reverse('public-today') + '?date={}&thread={}'.format(period.get_canonical_date(), thread.name))

    canonical_date = period.get_canonical_date()

    next_period = period.get_next()
    prev_period = period.get_previous()

    today_plan = get_or_initial(Plan, pub_date=canonical_date, thread=thread)
    tomorrow_plan = get_or_initial(Plan, pub_date=next_period.get_canonical_date(), thread=thread)
    reflection = get_or_initial(Reflection, pub_date=canonical_date, thread=thread)

    habits = Habit.objects.all()
    tracked_habits = HabitTracked.objects.filter(
         published__range=period.as_tuple()
    )

    if request.method == 'POST':
        plan = PlanForm(request.POST, instance=today_plan, prefix="today_plan")
        tomorrow_plan = PlanForm(request.POST, instance=tomorrow_plan, prefix="tomorrow_plan")
        reflection = ReflectionForm(request.POST, instance=reflection, prefix="reflection")

        today_valid, today_plan_form = validate_form_and_perform_save_or_delete(plan, ['focus', 'want'])
        tomorrow_valid, tomorrow_plan_form = validate_form_and_perform_save_or_delete(tomorrow_plan, ['focus', 'want'])
        reflection_valid, reflection_form = validate_form_and_perform_save_or_delete(reflection, ['good', 'better', 'best'])

        if all((today_valid, tomorrow_valid, reflection_valid)):
            return redirect(request.get_full_path())

    else:
        today_plan_form = PlanForm(instance=today_plan, prefix="today_plan")
        tomorrow_plan_form = PlanForm(instance=tomorrow_plan, prefix="tomorrow_plan")
        reflection_form = ReflectionForm(instance=reflection, prefix="reflection")

    journals = JournalAdded.objects.filter(
        published__range=period.as_tuple(),
        thread=thread,
    ).order_by('published')

    actual_today = timezone.now().date()

    return render(request, 'today.html', {
        'yesterday': prev_period.get_canonical_date(),
        'today': canonical_date,
        'actual_today': actual_today,
        'is_today': canonical_date == actual_today,
        'tomorrow': next_period.get_canonical_date(),
        'today_plan': today_plan,
        'tomorrow_plan': tomorrow_plan,
        'reflection': reflection,
        'larger_plans': get_larger_plans(period, thread),

        'today_plan_form': today_plan_form,
        'tomorrow_plan_form': tomorrow_plan_form,
        'reflection_form': reflection_form,

        'habits': habits,
        'tracked_habits': tracked_habits,

        'thread': thread,
        'threads': Thread.objects.all(),

        'journals': journals,
        'event_calendar': event_calendar(period.start - datetime.timedelta(weeks=52), period.end),
        'weekly_summary_calendar': weekly_summary_calendar((period.start - datetime.timedelta(weeks=52)).date(), period.end.date()),
        'monthly_summary_calendar': monthly_summary_calendar((period.start - datetime.timedelta(weeks=52)).date(), period.end.date()),
    })
