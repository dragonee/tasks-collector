from django.shortcuts import render, get_object_or_404
from django.http import HttpRequest
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from django.views.generic import ListView

from django.db.models import Max

from rest_framework import viewsets
from rest_framework.exceptions import MethodNotAllowed

from .models import QuestJournal, Quest
from .serializers import QuestSerializer, QuestJournalSerializer



class QuestViewSet(viewsets.ModelViewSet):
    queryset = Quest.objects.all()
    serializer_class = QuestSerializer


class QuestJournalViewSet(viewsets.ModelViewSet):
    queryset = QuestJournal.objects.all()
    serializer_class = QuestJournalSerializer

    def update(self, request, pk=None):
        raise MethodNotAllowed(request.method)

    def partial_update(self, request, pk=None):
        raise MethodNotAllowed(request.method)

@login_required
def show_quest(request: HttpRequest, slug: str):
    return render(request, "quests/single.html", {
        "quest": get_object_or_404(Quest, slug=slug),
    })

class QuestListView(LoginRequiredMixin, ListView):
    model = Quest

    queryset = Quest.objects.all().annotate(
        last_id=Max('questjournal__pk'),
    ).order_by('-last_id')

    paginate_by = 100

class QuestJournalListView(LoginRequiredMixin, ListView):
    model = QuestJournal

    queryset = QuestJournal.objects.order_by('-pk')

    paginate_by = 400
