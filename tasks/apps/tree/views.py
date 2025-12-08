from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from rest_framework import viewsets
from rest_framework import status

from .serializers import *
from .models import *
from .forms import *
from .habits import habits_line_to_habits_tracked
from .board_operations import add_task_to_board

from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django_htmx.http import retarget, HttpResponseClientRefresh

from rest_framework.response import Response as RestResponse
from rest_framework.decorators import api_view

from django.utils import timezone


from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend

from django.db import transaction

from django.contrib import messages

from django.views.generic.dates import MonthArchiveView

from .utils.statistics import get_aggregate_statistics
from .utils.datetime import (
    make_last_day_of_the_week,
    make_last_day_of_the_month,
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

    pagination_class = None

class ProfileViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProfileSerializer
    
    def get_queryset(self):
        # Only return the current user's profile
        return Profile.objects.filter(user=self.request.user)

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

def _add_task_to_plan(text, timeframe):
    """Helper function to add a task to a plan

    Args:
        text: The task text to add
        timeframe: One of 'today', 'tomorrow', 'this_week'

    Returns:
        The Plan object that was created or updated
    """
    from datetime import date, timedelta

    if timeframe == 'today':
        focus_date = date.today()
        thread = Thread.objects.get(name='Daily')
    elif timeframe == 'tomorrow':
        focus_date = date.today() + timedelta(days=1)
        thread = Thread.objects.get(name='Daily')
    elif timeframe == 'this_week':
        focus_date = make_last_day_of_the_week(date.today())
        thread = Thread.objects.get(name='Weekly')
    else:
        raise ValueError(f"Invalid timeframe: {timeframe}")

    plan, created = Plan.objects.get_or_create(
        pub_date=focus_date,
        thread=thread,
        defaults={'focus': text}
    )
    if not created:
        # Check if the text already exists in the plan (prevent duplicates)
        if plan.focus:
            existing_lines = plan.focus.split('\n')
            if text not in existing_lines:
                plan.focus += '\n' + text
                plan.save()
            # If text already exists, don't add it again (but still return success)
        else:
            plan.focus = text
            plan.save()

    return plan


@api_view(['POST'])
def add_task_to_plan(request):
    """Add a task to a plan (today, tomorrow, or this week)"""
    task_text = request.data.get('text')
    timeframe = request.data.get('timeframe')  # 'today', 'tomorrow', 'this_week'

    if not task_text or not timeframe:
        return RestResponse(
            {'error': 'text and timeframe are required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        plan = _add_task_to_plan(task_text, timeframe)
        return RestResponse(
            {
                'success': True,
                'plan_id': plan.id,
                'plan_date': plan.pub_date,
            },
            status=status.HTTP_200_OK
        )
    except Thread.DoesNotExist:
        return RestResponse(
            {'error': 'Required thread not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except ValueError as e:
        return RestResponse(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

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
        add_task_to_board(content, 'Inbox')
    elif content_type == 'plan_focus':
        timeframe = form.cleaned_data['focus_timeframe']
        _add_task_to_plan(content, timeframe)

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


@login_required
def stats(request):
    try:
        year = int(request.GET.get('year'))
    except (ValueError, TypeError):
        year = None

    return render(request, "tree/stats.html", get_aggregate_statistics(year))

@api_view(['GET'])
def stats_json(request):
    try:
        year = int(request.GET.get('year'))
    except (ValueError, TypeError):
        year = None

    return RestResponse(get_aggregate_statistics(year))

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

@login_required
@transaction.atomic
def journal_add(request):
    """View to add a journal entry via web form"""
    if request.method == 'POST':
        form = JournalAddedForm(request.POST)
        if form.is_valid():
            journal_added = form.save()
            
            # Replicate API behavior: add reflection items and extract habits
            add_reflection_items(journal_added)
            
            # Handle reflect command
            if 'reflection' not in request.POST:
                triplets = habits_line_to_habits_tracked(journal_added.comment)
                
                for occured, habit, note in triplets:
                    HabitTracked.objects.create(
                        occured=occured,
                        habit=habit,
                        note=note,
                        published=journal_added.published,
                        thread=Thread.objects.get(name='Daily'),
                    )
            
            from django.utils import timezone
            messages.success(request, 'Journal entry added successfully!')
            today_str = timezone.now().date().isoformat()
            return redirect(f"{reverse('public-today')}?date={today_str}")
    else:
        form = JournalAddedForm()
    
    return render(request, 'tree/journal_add.html', {
        'form': form,
    })

