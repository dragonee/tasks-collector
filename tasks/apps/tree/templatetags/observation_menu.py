from django import template

from ..models import InsightRefined, Observation, ObservationClosed

register = template.Library()


@register.inclusion_tag("tree/_observation_menu.html", takes_context=True)
def observation_menu(context, attach_mode=False):
    request = context["request"]

    active = getattr(request.resolver_match, "url_name", None)

    return {
        "mine_count": Observation.objects.filter(user=request.user).count(),
        "open_count": Observation.objects.count(),
        "closed_count": ObservationClosed.objects.count(),
        "insights_count": (
            InsightRefined.objects.values("event_stream_id").distinct().count()
        ),
        "attach_mode": attach_mode,
        "active": active,
    }
