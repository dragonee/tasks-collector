from django.shortcuts import render

from rest_framework import viewsets

from .serializers import BoardSerializer
from .models import Board


class BoardViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """
    queryset = Board.objects.all()
    serializer_class = BoardSerializer