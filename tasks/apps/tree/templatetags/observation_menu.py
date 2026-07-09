from django import template

from ..models import InsightRefined, Observation, ObservationClosed, ObservationType

register = template.Library()

# Keep in sync with ObservationListFilterMixin in views_observation.py.
SORT_CHOICES = ("added", "modified")
DEFAULT_SORT = "added"


@register.inclusion_tag("tree/_observation_menu.html", takes_context=True)
def observation_menu(context, attach_mode=False):
    request = context["request"]

    active = getattr(request.resolver_match, "url_name", None)

    current_sort = request.GET.get("sort")
    if current_sort not in SORT_CHOICES:
        current_sort = DEFAULT_SORT

    return {
        "mine_count": Observation.objects.filter(user=request.user).count(),
        "open_count": Observation.objects.count(),
        "closed_count": ObservationClosed.objects.count(),
        "insights_count": (
            InsightRefined.objects.values("event_stream_id").distinct().count()
        ),
        "observation_types": ObservationType.objects.order_by("name"),
        "current_type": request.GET.get("type") or "",
        "current_sort": current_sort,
        "attach_mode": attach_mode,
        "active": active,
    }
