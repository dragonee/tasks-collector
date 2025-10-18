from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.forms import inlineformset_factory
from django.urls import reverse

from rest_framework.decorators import api_view
from rest_framework.response import Response as RestResponse
from rest_framework import status

from .models import (
    Breakthrough,
    ProjectedOutcome,
    ProjectedOutcomeClosed,
    HabitTracked,
)
from .forms import BreakthroughForm, ProjectedOutcomeForm


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

    # Get closed ProjectedOutcomes for this year's breakthrough
    if breakthrough.pk:
        closed_outcomes = ProjectedOutcomeClosed.objects.filter(
            breakthrough=breakthrough
        ).order_by('-published')
    else:
        closed_outcomes = ProjectedOutcomeClosed.objects.none()

    return render(request, "tree/breakthrough.html", {
        'year': year,
        'breakthrough_habits': breakthrough_habits,
        'form': form,
        'formset': formset,
        'projected_outcome_queryset': projected_outcome_queryset,
        'closed_outcomes': closed_outcomes,
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


@api_view(['POST'])
def projected_outcome_close(request, projected_outcome_id):
    projected_outcome = get_object_or_404(ProjectedOutcome, pk=projected_outcome_id)

    projected_outcome_closed = ProjectedOutcomeClosed.from_projected_outcome(projected_outcome)

    with transaction.atomic():
        projected_outcome_closed.save()

        projected_outcome.delete()

    response = RestResponse({'ok': True}, status=status.HTTP_200_OK)
    response['HX-Redirect'] = reverse('breakthrough', args=[projected_outcome.breakthrough.slug])

    return response
