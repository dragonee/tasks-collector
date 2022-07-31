from django.shortcuts import render, get_object_or_404
from django.http import HttpRequest

from rest_framework import viewsets
from rest_framework.exceptions import MethodNotAllowed

from .models import QuestJournal, Quest
from .serializers import QuestSerializer, QuestJournalSerializer

def disabled_method(*args, **kwargs):
    raise MethodNotAllowed(request.method)


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

def show_quest(request: HttpRequest, slug: str):
    return render(request, "quests/single.html", {
        "quest": get_object_or_404(Quest, slug=slug),
    })