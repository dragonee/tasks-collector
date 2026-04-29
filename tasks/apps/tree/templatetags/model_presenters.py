from datetime import date

from django import template
from django.template.defaultfilters import date as date_filter
from django.template.defaultfilters import linebreaks, stringfilter
from django.utils.safestring import mark_safe

from ..forms import OnlyTextSingleHabitTrackedForm

register = template.Library()


@register.filter
@stringfilter
def first_line(text):
    splitted = text.split("\n")

    if len(splitted) > 1:
        return splitted[0].rstrip().rstrip(".…") + "…"

    return text


@register.filter
def get_habit_form(journal_added):
    return OnlyTextSingleHabitTrackedForm(
        initial={
            "journal": journal_added,
        }
    )


import re


def get_habit_pattern(habit):
    return re.compile(r"^[#!]" + re.escape(habit.name) + r"\s+", re.IGNORECASE)


@register.filter
def habit_without_name(tracked):
    return re.sub(get_habit_pattern(tracked.habit), "", tracked.note)


@register.filter
def missing_months(regrouped_habits):
    year = regrouped_habits[0][1][0].published.year

    months = [date_filter(date(year, month, 1), "F Y") for month in range(1, 13)]

    def pair_iterators(full_iter, partial_iter):
        full_iter = iter(full_iter)
        partial_iter = iter(partial_iter)

        full_item = next(full_iter, None)
        partial_item = next(partial_iter, None)

        while full_item is not None:
            if partial_item is not None and full_item == partial_item[0]:
                yield (full_item, partial_item[1])
                partial_item = next(partial_iter, None)
            else:
                yield (full_item, [])
            full_item = next(full_iter, None)

    return pair_iterators(months, regrouped_habits)
