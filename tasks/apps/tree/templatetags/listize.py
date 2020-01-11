from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def listize(value):
    if not value.strip():
        return ""

    return mark_safe("<ul>" + "\n".join(map(lambda x: "<li>" + x.strip() + "</li>", value.splitlines())) + "</ul>")