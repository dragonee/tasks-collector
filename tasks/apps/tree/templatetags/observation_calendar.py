import datetime
from collections import Counter

from django import template
from django.utils import timezone

from ..models import ObservationMade
from ..utils.datetime import DayCount, adjust_start_date_to_monday, date_range_generator
from ..utils.itertools import itemize

register = template.Library()


def _observation_calendar(start, end):
    events = (
        ObservationMade.objects.filter(
            published__range=(start, end),
        )
        .order_by("published")
        .values("published")
    )

    c = Counter()

    for event in events:
        c[event["published"].date()] += 1

    return c


def observation_calendar_data(end):
    start = end - datetime.timedelta(weeks=52)
    start = adjust_start_date_to_monday(start)

    return list(
        itemize(
            date_range_generator(start, end),
            _observation_calendar(start, end),
            default=0,
            item_type=DayCount,
        )
    )


@register.inclusion_tag("tree/_observation_calendar.html")
def observation_calendar():
    end = timezone.now()
    return {
        "observation_calendar": observation_calendar_data(end),
    }
