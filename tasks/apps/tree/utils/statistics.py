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
    ProjectedOutcomeMade,
    ProjectedOutcomeRedefined,
    ProjectedOutcomeRescheduled,
    Statistics,
)
from .itertools import _in_second, compose


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


def calculate_total_word_count(year=None):
    """Calculate total word count from all events and plans with text content

    Reflections are not counted as they most often just repeat the text found in journal entries.

    Args:
        year (int, optional): Filter by year. If None, includes all records.
    """
    total_words = 0

    # Count words from Events
    events = Event.objects.all()
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
    plans = Plan.objects.all()
    if year:
        plans = plans.filter(pub_date__year=year)

    for plan in plans:
        if plan.focus:
            total_words += count_words_in_text(plan.focus)
        if plan.want:
            total_words += count_words_in_text(plan.want)

    return total_words


def update_word_count_statistic(year=None):
    """Update or create the word count statistic

    Args:
        year (int, optional): Year to calculate for. If None, calculates for all events.
    """
    total_words = calculate_total_word_count(year)

    # Create key based on year
    key = f"total_word_count_{year}" if year else "total_word_count"

    # Update or create the statistic
    stat, created = Statistics.objects.get_or_create(
        key=key, defaults={"value": total_words}
    )

    if not created:
        stat.value = total_words
        stat.save()

    return total_words


def get_all_years_in_database():
    """Get all years that have events in the database"""
    years = Event.objects.dates("published", "year").values_list(
        "published__year", flat=True
    )
    return list(set(years))


def update_all_word_count_statistics():
    """Update word count statistics for all years and overall total

    Only updates current year and previous year if they already exist.
    Creates statistics for other years only if they don't exist.

    Returns:
        dict: Dictionary with 'total' and 'years' containing word counts
    """
    results = {}

    # Update overall total (always update)
    total_words = update_word_count_statistic()
    results["total"] = total_words

    # Get current and previous year
    current_year = timezone.now().year
    previous_year = current_year - 1

    # Get all years in database
    years = get_all_years_in_database()
    results["years"] = {}

    for year in sorted(years):
        # Always update current and previous year
        if year in [current_year, previous_year]:
            year_words = update_word_count_statistic(year=year)
            results["years"][year] = year_words
        else:
            # Only create if doesn't exist for other years
            key = f"total_word_count_{year}"
            try:
                stat = Statistics.objects.get(key=key)
                results["years"][year] = stat.value  # Use existing value
            except Statistics.DoesNotExist:
                # Create new statistic for this year
                year_words = update_word_count_statistic(year=year)
                results["years"][year] = year_words

    return results


def get_word_count_statistic(year=None):
    """Get the current word count statistic

    Args:
        year (int, optional): Year to get statistic for. If None, gets overall statistic.
    """
    key = f"total_word_count_{year}" if year else "total_word_count"

    try:
        stat = Statistics.objects.get(key=key)
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
    "event_count": Event,
}


def get_aggregate_statistics(year=None):
    """Get aggregate statistics for all events and activities

    Args:
        year (int, optional): Year to filter statistics by. If None, includes all records.

    Returns:
        dict: Dictionary containing counts for various event types and word counts
    """

    if year:
        year_filter = lambda qs: qs.filter(published__year=year)
    else:
        year_filter = lambda qs: qs

    _count_with_year_filter = compose(
        lambda model: model.objects.all(),
        year_filter,
        lambda qs: qs.count(),
    )

    all_counts = dict(
        map(_in_second(_count_with_year_filter), aggregate_models_dict.items())
    )

    # Get word count statistic
    word_count, word_count_updated = get_word_count_statistic(year=year)

    return all_counts | {
        "year": year,
        "years": list(range(timezone.now().year, 2018, -1)),
        "word_count": word_count,
        "word_count_updated": word_count_updated,
    }
