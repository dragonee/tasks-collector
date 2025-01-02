from django import template

from django.template.defaultfilters import linebreaks
from django.utils.safestring import mark_safe
from django.template.defaultfilters import stringfilter

from ..forms import OnlyTextSingleHabitTrackedForm


register = template.Library()


@register.filter
@stringfilter
def first_line(text):
    splitted = text.split('\n')

    if len(splitted) > 1:
        return splitted[0].rstrip().rstrip('.…') + '…'

    return text

@register.filter
def get_habit_form(journal_added):
    return OnlyTextSingleHabitTrackedForm(
        initial={
            'journal': journal_added,
        }
    )