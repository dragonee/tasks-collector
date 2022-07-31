from django.shortcuts import render
from django.http import HttpRequest, Http404, JsonResponse

from rest_framework import viewsets

from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect

from datetime import date

from .models import DataclassJSONEncoder, claim_reward, Claim, Claimed
from .serializers import ClaimSerializer, ClaimedSerializer

from django.db import transaction


class ClaimViewSet(viewsets.ModelViewSet):
    queryset = Claim.objects.all()
    serializer_class = ClaimSerializer


class ClaimedViewSet(viewsets.ModelViewSet):
    queryset = Claimed.objects.all()
    serializer_class = ClaimedSerializer


def claim_view(request: HttpRequest, id: int):
    try:
        return claimed_view(request, id)
    except Http404:
        pass
    
    claim = get_object_or_404(Claim, pk=id)
    
    if request.method == "POST":
        claimed = Claimed(
            claimed=claim_reward(claim.reward),
            claimed_date = date.today(),
            pk=claim.pk,
        )

        with transaction.atomic():
            claimed.save()
            claim.delete()

        if request.accepts("text/html"):
            return redirect('claim', id=claimed.pk)

        if request.accepts("application/json"):
            return JsonResponse(
                ClaimedSerializer(claimed).data,
                encoder=DataclassJSONEncoder,
            )

        raise Http404

    return render(request, "rewards/claim.html", {
        "claim": claim,
    })


def claimed_view(request: HttpRequest, id: int):
    return render(request, "rewards/claimed.html", {
        "claim": get_object_or_404(Claimed, pk=id),
    })