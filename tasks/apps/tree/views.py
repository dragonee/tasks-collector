from datetime import date as date_cls

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import prefetch_related_objects
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic.dates import MonthArchiveView

from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response as RestResponse

from .forms import *
from .models import *
from .presenters import load_other_observations
from .serializers import *
from .services.journalling import process_journal_entry
from .services.photos import attach_photo_urls
from .services.tasks import documents
from .services.today import plan_tasks, plan_text
from .utils.datetime import make_last_day_of_the_month, make_last_day_of_the_week
from .utils.statistics import get_aggregate_statistics
from .views_sharing import board_sharing_panels


class PlanFilter(filters.FilterSet):
    # Thread names are unique per user only: ?thread=Weekly means the
    # caller's Weekly thread.
    thread = filters.CharFilter(method="filter_thread")

    def filter_thread(self, queryset, name, value):
        return queryset.filter(thread__user=self.request.user, thread__name=value)

    class Meta:
        model = Plan
        fields = {
            "pub_date": ("gte", "lte", "exact"),
        }


class PlanViewSet(viewsets.ModelViewSet):
    # The class queryset only names the router basename; see get_queryset.
    queryset = Plan.objects.none()
    serializer_class = PlanSerializer

    filter_backends = [DjangoFilterBackend]
    filterset_class = PlanFilter

    def get_queryset(self):
        return Plan.objects.filter(thread__user=self.request.user)

    # Text written here is a plan: its lines become tasks.
    def perform_create(self, serializer):
        documents.sync_lines(serializer.save(), create_tasks=True)

    def perform_update(self, serializer):
        documents.sync_lines(serializer.save(), create_tasks=True)

    def perform_destroy(self, instance):
        documents.delete(instance)


class ReflectionViewSet(viewsets.ModelViewSet):
    queryset = Reflection.objects.none()
    serializer_class = ReflectionSerializer

    def get_queryset(self):
        return Reflection.objects.filter(thread__user=self.request.user)

    def perform_create(self, serializer):
        documents.sync_lines(serializer.save(), create_tasks=False)

    def perform_update(self, serializer):
        documents.sync_lines(serializer.save(), create_tasks=False)


# XXX should we permit only POST here?
class JournalAddedViewSet(viewsets.ModelViewSet):
    queryset = JournalAdded.objects.none()
    serializer_class = JournalAddedSerializer

    def get_queryset(self):
        return (
            JournalAdded.objects.owned_by(self.request.user)
            .select_related("thread")
            .prefetch_related("tags")
        )

    @transaction.atomic
    def perform_create(self, serializer):
        journal_added = serializer.save(created_by=self.request.user)
        skip_habits = "reflection" in self.request.data
        story = serializer.validated_data.get("story")
        process_journal_entry(
            journal_added,
            skip_habits=skip_habits,
            story=story,
            user=self.request.user,
        )


class ThreadPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class ThreadViewSet(viewsets.ReadOnlyModelViewSet):
    # Read-only: thread names are looked up by literal value all over the code
    # ("Daily", "Weekly", ...), so a rename breaks them, and deleting a thread
    # cascades to every event, board, plan and reflection filed under it.
    # The class queryset only names the router basename; see get_queryset.
    queryset = Thread.objects.none()
    serializer_class = ThreadSerializer
    pagination_class = ThreadPagination

    def get_queryset(self):
        # The user's threads, then the boards shared with them to edit, so the
        # board page can open those too (``shared_by`` names their owner).
        return Thread.objects.board_editable_by(self.request.user).select_related(
            "user"
        )


class ProfileViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProfileSerializer

    def get_queryset(self):
        # Only return the current user's profile
        return (
            Profile.objects.filter(user=self.request.user)
            .select_related("default_board_thread__user")
            .prefetch_related("habit_keywords__habit__keywords")
        )


class StoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StorySerializer

    def get_queryset(self):
        # Only the current user's stories; `?active=true` limits to unstopped.
        qs = Story.objects.filter(user=self.request.user)
        if self.request.query_params.get("active") in ("1", "true", "True", "yes"):
            qs = qs.filter(stopped__isnull=True)
        return qs


def _add_task_to_plan(user, text, timeframe, today=None):
    """Helper function to add a task to one of ``user``'s plans

    Args:
        user: The owner of the plan's thread
        text: The task text to add
        timeframe: One of 'today', 'tomorrow', 'this_week'
        today: The day it is for the user. Defaults to the server's, which
            is a different day for part of every night.

    Returns:
        The Plan object that was created or updated
    """
    from datetime import date, timedelta

    if today is None:
        today = date.today()

    if timeframe == "today":
        focus_date = today
        thread_name = Thread.DAILY
    elif timeframe == "tomorrow":
        focus_date = today + timedelta(days=1)
        thread_name = Thread.DAILY
    elif timeframe == "this_week":
        focus_date = make_last_day_of_the_week(today)
        thread_name = Thread.WEEKLY
    else:
        raise ValueError(f"Invalid timeframe: {timeframe}")

    # The text is that of a board item, of whichever board the user had open.
    return plan_text(user, text, thread_name, focus_date, today, any_board=True)


@api_view(["POST"])
def add_task_to_plan(request):
    """Add a task to a plan (today, tomorrow, or this week)"""
    task_text = request.data.get("text")
    timeframe = request.data.get("timeframe")  # 'today', 'tomorrow', 'this_week'

    if not task_text or not timeframe:
        return RestResponse(
            {"error": "text and timeframe are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # The caller's own day (YYYY-MM-DD); optional for clients that predate it.
    today = None
    if request.data.get("date"):
        try:
            today = date_cls.fromisoformat(str(request.data["date"]))
        except ValueError:
            return RestResponse(
                {"error": "date must be YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    try:
        plan = _add_task_to_plan(request.user, task_text, timeframe, today=today)
        return RestResponse(
            {
                "success": True,
                "plan_id": plan.id,
                "plan_date": plan.pub_date,
            },
            status=status.HTTP_200_OK,
        )
    except Thread.DoesNotExist:
        return RestResponse(
            {"error": "Required thread not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except ValueError as e:
        return RestResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


def _serialize_plan(user, pub_date, thread_name):
    """Build the {thread, pub_date, tasks:[{text, done}]} payload for one of
    ``user``'s plans, delegating the crossed-off computation to the today
    service."""
    return {
        "thread": thread_name,
        "pub_date": pub_date.isoformat(),
        "tasks": [
            {
                "text": t.text,
                "done": t.done,
                "mark": t.mark,
                # None for a plain line: one nothing was done with as a task.
                "id": t.id,
                "anchor": t.anchor,
                "total": t.total,
                "done_count": t.done_count,
            }
            for t in plan_tasks(user, pub_date, thread_name)
        ],
    }


@api_view(["GET"])
def today_plans(request):
    """Return the Daily / Weekly / Big-picture plans for the journal template,
    each task flagged with whether it has been crossed off (i.e. the line also
    appears in that day's Reflection.good). Powers the CLI `journal` command.

    The Daily plan is for ``date`` (a YYYY-MM-DD query param, the caller's
    local day; defaults to the server's today), the Weekly plan for the end of
    that week, and the Big-picture plan for the end of that month.
    """
    raw_date = request.query_params.get("date")
    if raw_date:
        try:
            pub_date = date_cls.fromisoformat(raw_date)
        except ValueError:
            return RestResponse(
                {"error": "date must be YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        pub_date = date_cls.today()

    return RestResponse(
        {
            "daily": _serialize_plan(request.user, pub_date, Thread.DAILY),
            "weekly": _serialize_plan(
                request.user, make_last_day_of_the_week(pub_date), Thread.WEEKLY
            ),
            "monthly": _serialize_plan(
                request.user, make_last_day_of_the_month(pub_date), Thread.BIG_PICTURE
            ),
        },
        status=status.HTTP_200_OK,
    )


### XXX TODO
### finish the editing views
### add auto-delete mechanism
class JournalArchiveContextMixin:
    def get_order(self):
        return self.request.GET.get("order", "desc")

    def get_queryset(self):
        queryset = super().get_queryset().owned_by(self.request.user)

        return queryset.order_by(
            "published" if self.get_order() == "asc" else "-published"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order"] = self.get_order()
        context["dates"] = self.get_queryset().dates("published", "month", order="DESC")
        context["tags"] = JournalTag.objects.filter(user=self.request.user)

        # Render trip photos and badges the same way today.html does: presign
        # thumbnails and prefetch the trip each entry is part of (one query for
        # the whole month, no per-entry lookup for the badge). Materialise so
        # the attributes survive the template's repeated iteration of the list.
        entries = list(context["object_list"])
        prefetch_related_objects(entries, Event.prefetch_trip())
        attach_photo_urls(entries)
        context["object_list"] = entries

        return context


class EventArchiveContextMixin:
    def get_queryset(self):
        return super().get_queryset().owned_by(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dates"] = Event.objects.owned_by(self.request.user).dates(
            "published", "month", order="DESC"
        )

        # Photo entries render with presigned URLs and a trip badge, as in the
        # diary; without the URLs the template fails on any month with a photo.
        events = list(context["object_list"])
        prefetch_related_objects(events, Event.prefetch_trip())
        Event.prefetch_related_by_kind(events, {HabitTracked: ["habit"]})
        ObservationEventMixin.prefetch_situations(events)
        load_other_observations(events, self.request.user)
        attach_photo_urls(events)
        context["object_list"] = events

        return context


class CurrentMonthArchiveView(LoginRequiredMixin, MonthArchiveView):
    allow_empty = True

    def get_month(self):
        return timezone.now().month

    def get_year(self):
        return timezone.now().year

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_current_month"] = True
        return context


class JournalCurrentMonthArchiveView(
    JournalArchiveContextMixin, CurrentMonthArchiveView
):
    model = JournalAdded
    date_field = "published"
    allow_future = True

    template_name = "tree/journaladded_archive_month.html"


class JournalArchiveMonthView(
    LoginRequiredMixin, JournalArchiveContextMixin, MonthArchiveView
):
    model = JournalAdded
    date_field = "published"
    allow_future = True


class JournalTagArchiveContextMixin(JournalArchiveContextMixin):
    """The diary filtered to one of the user's tags; any other slug is 404."""

    def get_tag(self):
        if not hasattr(self, "_tag"):
            self._tag = get_object_or_404(
                JournalTag, user=self.request.user, slug=self.kwargs["slug"]
            )
        return self._tag

    def get_queryset(self):
        return super().get_queryset().filter(tags=self.get_tag())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["tag"] = self.get_tag()

        return context


class JournalTagArchiveMonthView(
    LoginRequiredMixin, JournalTagArchiveContextMixin, MonthArchiveView
):
    model = JournalAdded
    date_field = "published"
    allow_future = True

    template_name = "tree/journaladded_archive_month.html"


class JournalTagCurrentMonthArchiveView(
    JournalTagArchiveContextMixin, CurrentMonthArchiveView
):
    model = JournalAdded
    date_field = "published"
    allow_future = True

    template_name = "tree/journaladded_archive_month.html"


class EventCurrentMonthArchiveView(EventArchiveContextMixin, CurrentMonthArchiveView):
    model = Event
    date_field = "published"
    allow_future = True


class EventArchiveMonthView(
    LoginRequiredMixin, EventArchiveContextMixin, MonthArchiveView
):
    model = Event
    date_field = "published"
    allow_future = True


@login_required
def stats(request):
    try:
        year = int(request.GET.get("year"))
    except ValueError, TypeError:
        year = None

    return render(
        request, "tree/stats.html", get_aggregate_statistics(request.user, year)
    )


@api_view(["GET"])
def stats_json(request):
    try:
        year = int(request.GET.get("year"))
    except ValueError, TypeError:
        year = None

    return RestResponse(get_aggregate_statistics(request.user, year))


@api_view(["GET"])
def daily_events(request):
    day = request.GET.get("date", timezone.now().date())

    thread_name = request.GET.get("thread", Thread.DAILY)
    thread = Thread.objects.filter(user=request.user, name=thread_name).first()

    events = list(
        Event.objects.owned_by(request.user)
        .filter(published__date=day, thread=thread)
        # Not completions: clients of this endpoint know a closed set of
        # event types; they read what was done from the reflection.
        .not_instance_of(BoardCommitted, TaskCompleted)
        .select_related("thread")
    )
    Event.prefetch_related_by_kind(
        events,
        {
            JournalAdded: ["tags"],
            HabitTracked: ["habit__keywords"],
            ObservationMade: ["type"],
            ObservationClosed: ["type"],
            InsightRefined: ["type"],
        },
    )
    ObservationEventMixin.prefetch_open_observation(events)
    ObservationEventMixin.prefetch_situations(events)
    plan = Plan.objects.filter(pub_date=day, thread=thread).first()
    reflection = Reflection.objects.filter(pub_date=day, thread=thread).first()

    return RestResponse(
        {
            "date": day,
            "events": EventSerializer(
                events, many=True, context={"request": request}
            ).data,
            "plan": (
                PlanSerializer(plan, context={"request": request}).data
                if plan
                else None
            ),
            "reflection": (
                ReflectionSerializer(reflection, context={"request": request}).data
                if reflection
                else None
            ),
        }
    )


@login_required
def account_settings(request):
    try:
        profile = Profile.objects.get(user=request.user)
    except Profile.DoesNotExist:
        profile = Profile(user=request.user)

    if request.method == "POST":
        profile_form = ProfileForm(request.POST, instance=profile, user=request.user)
        user_form = UserForm(request.POST, instance=request.user)
        if profile_form.is_valid() and user_form.is_valid():
            profile_form.save()
            user_form.save()
            messages.success(request, "Settings saved successfully!")
            return redirect("account-settings")
    else:
        profile_form = ProfileForm(instance=profile, user=request.user)
        user_form = UserForm(instance=request.user)

    return render(
        request,
        "tree/account_settings.html",
        {
            "profile_form": profile_form,
            "user_form": user_form,
            "profile": profile,
            "board_sharing": board_sharing_panels(request),
        },
    )


@login_required
def todo(request):
    try:
        profile = Profile.objects.get(user=request.user)
    except Profile.DoesNotExist:
        profile = None

    return render(
        request,
        "tree/tasks.html",
        {
            "profile": profile,
        },
    )


@login_required
@require_POST
def journal_entry_tag(request, journal_id):
    """Tag one of the user's journal entries, making the tag if it is new
    (the entry's "+Tag" form)."""
    journal = get_object_or_404(
        JournalAdded.objects.owned_by(request.user), pk=journal_id
    )
    form = JournalTagNameForm(request.POST, user=request.user)

    if not form.is_valid():
        return render(
            request,
            "tree/journal_tag/form.html",
            {"journal_id": journal.pk, "form": form},
            status=200 if request.htmx else 400,
        )

    tag = form.tag()
    journal.tags.add(tag)

    if not request.htmx:
        return redirect("public-diary-archive-current-month")

    return render(
        request,
        "tree/journal_tag/ok.html",
        {
            "tag": tag,
            "journal_id": journal.pk,
            "form": JournalTagNameForm(user=request.user),
        },
    )


@login_required
@transaction.atomic
def journal_add(request):
    """View to add a journal entry via web form"""
    if request.method == "POST":
        form = JournalAddedForm(request.POST, user=request.user)
        if form.is_valid():
            form.instance.created_by = request.user
            journal_added = form.save()
            skip_habits = "reflection" in request.POST
            process_journal_entry(
                journal_added, skip_habits=skip_habits, user=request.user
            )

            messages.success(request, "Journal entry added successfully!")
            today_str = timezone.now().date().isoformat()
            return redirect(f"{reverse('public-today')}?date={today_str}")
    else:
        form = JournalAddedForm(user=request.user)

    return render(
        request,
        "tree/journal_add.html",
        {
            "form": form,
        },
    )
