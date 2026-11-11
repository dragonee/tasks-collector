import datetime
from abc import ABC, abstractmethod
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import Habit, HabitTracked, JournalAdded, Plan, Thread
from .services.photos import attach_photo_urls
from .services.tasks import agenda, documents
from .services.tasks.documents import DocumentEdit
from .utils.datetime import (
    adjust_start_date_to_monday,
    make_last_day_of_the_month,
    make_last_day_of_the_week,
)


def make_aware_start(date):
    """Convert a date to timezone-aware datetime at the start of the day"""
    return timezone.make_aware(
        datetime.datetime.combine(date, datetime.datetime.min.time())
    )


def make_aware_end(date):
    """Convert a date to timezone-aware datetime at the end of the day"""
    return timezone.make_aware(
        datetime.datetime.combine(date, datetime.datetime.max.time())
    )


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
        prev_week_date = adjust_start_date_to_monday(self.date) - datetime.timedelta(
            days=7
        )
        return Weekly(prev_week_date).canonical()

    def get_next(self):
        """Get the next week (canonical = Sunday)"""
        next_week_date = make_last_day_of_the_week(self.date) + datetime.timedelta(
            days=1
        )
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


# The page's editors: (name of the form field, which document, which of its
# fields, the prompt shown while it is empty).
EDITORS = (
    ("today_plan-focus", "today_plan", "focus", "Today's focus"),
    ("tomorrow_plan-focus", "tomorrow_plan", "focus", "Tomorrow's focus"),
    ("reflection-good", "reflection", "good", "Good"),
    ("reflection-better", "reflection", "better", "Better"),
    ("reflection-best", "reflection", "best", "Best"),
)


def save_editors(post, sources):
    """Save what the page's editors hold. ``sources`` maps a document's name
    to ``(getter, thread, date)``, the getter being ``documents.plan_for`` or
    ``reflection_for``.

    Each editor posts its text, a line of a task ending with the task's
    anchor, and the text it was loaded with (``<name>-base``); only what
    differs between the two is applied (see ``DocumentEdit.apply``). A post
    without the base is plain text, written as such. The three documents are
    one edit: a line moved from today's plan to tomorrow's is the same task.
    A document left without a line is deleted.
    """
    edit = DocumentEdit()
    saved = {}

    for name, source, field, _prompt in EDITORS:
        if name not in post:
            continue
        text = post[name]
        getter, thread, pub_date = sources[source]

        if source not in saved:
            saved[source] = getter(thread, pub_date, create=bool(text.strip()))
        elif saved[source] is None and text.strip():
            saved[source] = getter(thread, pub_date, create=True)
        if saved[source] is None:
            continue

        base = post.get(f"{name}-base")
        if base is None:
            edit.write(saved[source], field, text)
        else:
            edit.apply(saved[source], field, text, base=base)

    edit.finish()

    for document in saved.values():
        if document is not None and not any(
            row.content.strip() for row in documents.rows(document)
        ):
            document.delete()


def is_before_noon():
    return timezone.now().hour < 12


def yesterday(date):
    return date - datetime.timedelta(days=1)


def get_period_by_thread(thread):
    if thread.name == Thread.WEEKLY:
        return Weekly
    elif thread.name == Thread.BIG_PICTURE:
        return Monthly
    else:
        return Daily


def get_larger_plan(period, thread):
    """The plan one level up (Daily -> Weekly -> big-picture) on the same
    user's thread, or None."""
    mapping = {
        Thread.WEEKLY: (Thread.BIG_PICTURE, Monthly),
        Thread.DAILY: (Thread.WEEKLY, Weekly),
    }

    try:
        larger_thread, larger_period_cls = mapping[thread.name]
    except KeyError:
        return None

    larger_period = larger_period_cls(period.get_canonical_date())

    try:
        return Plan.objects.select_related("thread").get(
            pub_date=larger_period.get_canonical_date(),
            thread__user_id=thread.user_id,
            thread__name=larger_thread,
        )
    except Plan.DoesNotExist:
        return None


def get_larger_plans(period, thread):
    plans = []

    larger_plan = get_larger_plan(period, thread)
    while larger_plan:
        plans.append(larger_plan)
        period = get_period_by_thread(larger_plan.thread)(larger_plan.pub_date)
        larger_plan = get_larger_plan(period, larger_plan.thread)

    return reversed(plans)


def get_period_from_request(request, thread):
    """Extract date from request and create appropriate period instance"""
    try:
        today = date.fromisoformat(request.GET["date"])
    except KeyError, ValueError:
        today = yesterday(date.today()) if is_before_noon() else date.today()

    period_cls = get_period_by_thread(thread)
    return period_cls(today)


@login_required
def today(request):
    if request.method == "POST":
        thread_name = request.POST.get("thread")
    else:
        thread_name = request.GET.get("thread", Thread.DAILY)

    thread = get_object_or_404(Thread, user=request.user, name=thread_name)

    period = get_period_from_request(request, thread)

    if not period.is_canonical():
        return redirect(
            reverse("public-today")
            + "?date={}&thread={}".format(period.get_canonical_date(), thread.name)
        )

    canonical_date = period.get_canonical_date()

    next_period = period.get_next()
    prev_period = period.get_previous()

    sources = {
        "today_plan": (documents.plan_for, thread, canonical_date),
        "tomorrow_plan": (
            documents.plan_for,
            thread,
            next_period.get_canonical_date(),
        ),
        "reflection": (documents.reflection_for, thread, canonical_date),
    }

    if request.method == "POST":
        with transaction.atomic():
            save_editors(request.POST, sources)

        return redirect(request.get_full_path())

    habits = Habit.objects.filter(user=request.user)
    tracked_habits = HabitTracked.objects.filter(
        habit__user=request.user, published__range=period.as_tuple()
    ).select_related("habit")

    loaded = {
        source: getter(thread_, pub_date)
        for source, (getter, thread_, pub_date) in sources.items()
    }
    editors = {}
    page_tasks = {}
    for name, source, field, prompt in EDITORS:
        document = loaded[source]
        editors[name.replace("-", "_")] = {
            "name": name,
            "prompt": prompt,
            "kind": "plan" if source != "reflection" else "reflection",
            "text": (
                documents.render_anchored(document, field)
                if document is not None
                else ""
            ),
        }
        for row in documents.rows(document, field) if document is not None else []:
            if row.task_id:
                page_tasks[row.task.anchor] = row.task

    # What the editor draws each anchor with, by anchor.
    shown = agenda.describe(
        [agenda.task_shown(task, request.user) for task in page_tasks.values()],
        request.user,
    )
    chips = {
        task["anchor"]: {
            key: task[key]
            for key in ("id", "text", "display", "done", "total", "done_count")
        }
        for task in shown
    }

    larger_plans = [
        {"thread": plan.thread, "tasks": agenda.tasks_of(plan, request.user)}
        for plan in get_larger_plans(period, thread)
    ]

    # Materialise so we can attach presigned photo URLs; prefetch the trip
    # each entry is part of, so the per-entry trip badge costs no extra
    # query per journal entry.
    journals = list(
        JournalAdded.objects.filter(
            published__range=period.as_tuple(),
            thread=thread,
        )
        .prefetch_related(JournalAdded.prefetch_trip())
        .order_by("published")
    )
    attach_photo_urls(journals)

    actual_today = timezone.now().date()

    return render(
        request,
        "today.html",
        {
            "yesterday": prev_period.get_canonical_date(),
            "today": canonical_date,
            "actual_today": actual_today,
            "is_today": canonical_date == actual_today,
            "tomorrow": next_period.get_canonical_date(),
            "larger_plans": larger_plans,
            "editors": editors,
            "chips": chips,
            # The day a task ticked on this page is done on: the page's own
            # day for a daily page, the reader's today otherwise.
            "completion_day": canonical_date if thread.name == Thread.DAILY else None,
            "habits": habits,
            "tracked_habits": tracked_habits,
            "thread": thread,
            "threads": Thread.objects.for_user(request.user),
            "journals": journals,
            "period_is_single_day": period.start.date() == period.end.date(),
        },
    )
