from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Challenge, Element
from .serializers import ChallengeSerializer, ElementSerializer
from .services.evaluation import function_counts


class ElementViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Append-only: list and create only (no update/destroy)."""

    queryset = Element.objects.all()
    serializer_class = ElementSerializer


class ChallengeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Challenge.objects.all()
    serializer_class = ChallengeSerializer


@api_view(["GET"])
def summary(request):
    """Feeds the dashboard: lifetime totals across all elements, plus each
    active challenge with its progress and stage ladder."""
    challenges = Challenge.objects.filter(active=True)

    return Response(
        {
            "totals": function_counts(Element.objects.all()),
            "challenges": ChallengeSerializer(
                challenges, many=True, context={"request": request}
            ).data,
        }
    )


@login_required
def dashboard(request):
    return render(request, "enfp/dashboard.html", {})
