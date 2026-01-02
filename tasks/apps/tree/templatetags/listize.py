from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def listize(value):
    if not value.strip():
        return ""

    return mark_safe(
        "<ul>"
        + "\n".join(map(lambda x: "<li>" + x.strip() + "</li>", value.splitlines()))
        + "</ul>"
    )


from django.template.defaultfilters import slugify as _slugify

from unidecode import unidecode


@register.filter
def slugify(value):
    return _slugify(unidecode(str(value)))


@register.filter
def dots(value, max=3):
    return mark_safe('<span class="dot"></span> ' * min(max, value))


@register.filter
def max(value, max=4):
    return min(max, value)
