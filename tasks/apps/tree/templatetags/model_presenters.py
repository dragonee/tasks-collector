from django import template

from django.template.defaultfilters import linebreaks
from django.utils.safestring import mark_safe
from django.template.defaultfilters import stringfilter


register = template.Library()


@register.filter
def add_published(object):
    linebreaks_str = linebreaks(object.comment)

    time_str = '<p data-time="{}">'.format(
        object.published.strftime('%H:%M')
    )

    return mark_safe(linebreaks_str.replace('<p>', time_str, 1))


@register.filter
@stringfilter
def first_line(text):
    splitted = text.split('\n')

    if len(splitted) > 1:
        return splitted[0].rstrip().rstrip('.…') + '…'

    return text
