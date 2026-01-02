from calendar import monthrange
from collections import namedtuple
from datetime import datetime, timedelta

from django.utils import timezone


def aware_from_date(d):
    return timezone.make_aware(datetime.combine(d, datetime.min.time()))


DayCount = namedtuple("DayCount", ["date", "count"])


def date_range_generator(start, end):
    current = start

    while current <= end:
        yield current.date()
        current += timedelta(days=1)


def adjust_start_date_to_monday(date):
    if date.weekday() == 0:
        return date

    return date - timedelta(days=date.weekday())


def adjust_date_to_sunday(date):
    """Adjust date to the Sunday of its week (6 = Sunday in Python's weekday system)"""
    days_until_sunday = (6 - date.weekday()) % 7
    return date + timedelta(days=days_until_sunday)


def make_last_day_of_the_week(date):
    return date + timedelta(days=(6 - date.weekday()))


def make_last_day_of_the_month(date):
    return date.replace(day=monthrange(date.year, date.month)[1])


def get_week_period(date):
    """Get the (start, end) tuple for the week containing the given date"""
    monday = adjust_start_date_to_monday(date)
    sunday = monday + timedelta(days=6)
    return (monday, sunday)


def get_month_period(date):
    """Get the (start, end) tuple for the month containing the given date"""
    month_start = date.replace(day=1)
    month_end = date.replace(day=monthrange(date.year, date.month)[1])
    return (month_start, month_end)


def generate_periods(start, end, period_func):
    """Generate all periods between start and end using the given period function"""
    periods = []
    seen_periods = set()

    current = start
    while current <= end:
        period = period_func(current)
        if period not in seen_periods:
            periods.append(period)
            seen_periods.add(period)

        # Move forward by the period duration
        if period_func == get_week_period:
            current += timedelta(days=7)
        else:  # monthly
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    return periods
