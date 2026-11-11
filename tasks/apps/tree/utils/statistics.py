import re
from functools import reduce

from django.utils import timezone

from ..models import (
    Event,
    HabitTracked,
    JournalAdded,
    ObservationClosed,
    ObservationMade,
    ObservationRecontextualized,
    ObservationReflectedUpon,
    ObservationReinterpreted,
    ObservationUpdated,
    Plan,
    ProjectedOutcomeClosed,
    ProjectedOutcomeEvolved,
    ProjectedOutcomeMade,
    ProjectedOutcomeRedefined,
    ProjectedOutcomeRescheduled,
    Statistics,
)
from .itertools import _in_second, compose

# Statistics are per user. Events and plans belong to whoever owns the thread
# they are filed under.


def count_words_in_text(text):
    """Count words in a text string, excluding empty strings"""
    if not text or not isinstance(text, str):
        return 0
    # Split by whitespace and count non-empty strings
    return len([word for word in re.split(r"\s+", text.strip()) if word])


fields = [
    "comment",
    "note",
    "situation",
    "interpretation",
    "approach",
    "description",
    "name",
    "success_criteria",
]


def calculate_total_word_count(user, year=None):
    """Calculate total word count from ``user``'s events and plans with text
    content

    Reflections are not counted as they most often just repeat the text found in journal entries.

    Args:
        user: Whose events and plans to count.
        year (int, optional): Filter by year. If None, includes all records.
    """
    total_words = 0

    # Count words from Events
    events = Event.objects.filter(thread__user=user)
    if year:
        events = events.filter(published__year=year)

    for event in events:
        # Find all text fields present on this event
        filtered_fields = filter(lambda x: bool(getattr(event, x, None)), fields)

        # Create a list of all text fields for this event
        text_fields = reduce(
            lambda acc, x: acc + [getattr(event, x, None)], filtered_fields, []
        )

        # Count words in all text fields for this event
        for text in text_fields:
            total_words += count_words_in_text(text)

    # Count words from Plans
    plans = Plan.objects.filter(thread__user=user)
    if year:
        plans = plans.filter(pub_date__year=year)

    for plan in plans.prefetch_related("lines"):
        total_words += count_words_in_text(plan.focus)

    return total_words


def update_word_count_statistic(user, year=None):
    """Update or create ``user``'s word count statistic

    Args:
        user: Whose word count to update.
        year (int, optional): Year to calculate for. If None, calculates for all events.
    """
    total_words = calculate_total_word_count(user, year)

    # Create key based on year
    key = f"total_word_count_{year}" if year else "total_word_count"

    # Update or create the statistic
    stat, created = Statistics.objects.get_or_create(
        user=user, key=key, defaults={"value": total_words}
    )

    if not created:
        stat.value = total_words
        stat.save()

    return total_words


def get_all_years_in_database(user):
    """Get all years in which ``user`` has events"""
    years = (
        Event.objects.filter(thread__user=user)
        .dates("published", "year")
        .values_list("published__year", flat=True)
    )
    return list(set(years))


def update_all_word_count_statistics(user):
    """Update ``user``'s word count statistics for all years and overall total

    Only updates current year and previous year if they already exist.
    Creates statistics for other years only if they don't exist.

    Returns:
        dict: Dictionary with 'total' and 'years' containing word counts
    """
    results = {}

    # Update overall total (always update)
    total_words = update_word_count_statistic(user)
    results["total"] = total_words

    # Get current and previous year
    current_year = timezone.now().year
    previous_year = current_year - 1

    # Get all years in database
    years = get_all_years_in_database(user)
    results["years"] = {}

    for year in sorted(years):
        # Always update current and previous year
        if year in [current_year, previous_year]:
            year_words = update_word_count_statistic(user, year=year)
            results["years"][year] = year_words
        else:
            # Only create if doesn't exist for other years
            key = f"total_word_count_{year}"
            try:
                stat = Statistics.objects.get(user=user, key=key)
                results["years"][year] = stat.value  # Use existing value
            except Statistics.DoesNotExist:
                # Create new statistic for this year
                year_words = update_word_count_statistic(user, year=year)
                results["years"][year] = year_words

    return results


def get_word_count_statistic(user, year=None):
    """Get ``user``'s current word count statistic

    Args:
        user: Whose statistic to read.
        year (int, optional): Year to get statistic for. If None, gets overall statistic.
    """
    key = f"total_word_count_{year}" if year else "total_word_count"

    try:
        stat = Statistics.objects.get(user=user, key=key)
        return stat.value, stat.last_updated
    except Statistics.DoesNotExist:
        return None, None


aggregate_models_dict = {
    "journal_count": JournalAdded,
    "habit_count": HabitTracked,
    "observation_count": ObservationMade,
    "observation_updated_count": ObservationUpdated,
    "observation_closed_count": ObservationClosed,
    "observation_recontextualized_count": ObservationRecontextualized,
    "observation_reflected_upon_count": ObservationReflectedUpon,
    "observation_reinterpreted_count": ObservationReinterpreted,
    "projected_outcome_made_count": ProjectedOutcomeMade,
    "projected_outcome_redefined_count": ProjectedOutcomeRedefined,
    "projected_outcome_rescheduled_count": ProjectedOutcomeRescheduled,
    "projected_outcome_closed_count": ProjectedOutcomeClosed,
    "projected_outcome_evolved_count": ProjectedOutcomeEvolved,
    "event_count": Event,
}


def get_aggregate_statistics(user, year=None):
    """Get aggregate statistics for ``user``'s events and activities

    Args:
        user: Whose events to count.
        year (int, optional): Year to filter statistics by. If None, includes all records.

    Returns:
        dict: Dictionary containing counts for various event types and word counts
    """

    if year:
        year_filter = lambda qs: qs.filter(published__year=year)
    else:
        year_filter = lambda qs: qs

    _count_with_year_filter = compose(
        lambda model: model.objects.filter(thread__user=user),
        year_filter,
        lambda qs: qs.count(),
    )

    all_counts = dict(
        map(_in_second(_count_with_year_filter), aggregate_models_dict.items())
    )

    # Get word count statistic
    word_count, word_count_updated = get_word_count_statistic(user, year=year)

    return all_counts | {
        "year": year,
        "years": list(range(timezone.now().year, 2018, -1)),
        "word_count": word_count,
        "word_count_updated": word_count_updated,
    }
