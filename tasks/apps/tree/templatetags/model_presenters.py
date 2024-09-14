from django import template

from django.template.defaultfilters import linebreaks
from django.utils.safestring import mark_safe


register = template.Library()


@register.filter
def add_published(object):
    linebreaks_str = linebreaks(object.comment)

    time_str = '<p data-time="{}">'.format(
        object.published.strftime('%H:%M')
    )

    return mark_safe(linebreaks_str.replace('<p>', time_str, 1))


