from django.shortcuts import render

from rest_framework import viewsets

from .serializers import BoardSerializer
from .models import Board

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view

from django.utils import timezone

class BoardViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """
    queryset = Board.objects.all()
    serializer_class = BoardSerializer

def transition_markers_in_tree_item(markers):
    return {
        "weeksInList": markers['weeksInList'] + 1,
        "important": markers['important'],
        "finalizing": markers['finalizing'],
        "canBeDoneOutsideOfWork": markers['canBeDoneOutsideOfWork'],
        "canBePostponed": markers['canBePostponed'],
        "postponedFor": max(0, markers['postponedFor'] - 1),
    }

def transition_data_in_tree_item(item):
    return {
        "text": item['text'],
        "children": transition_data_between_boards(item['children']),

        "data": {
            "text": item['data']['text'],
            "state": item['data']['state'],
            "meaningfulMarkers": transition_markers_in_tree_item(item['data']['meaningfulMarkers']),
        },

        'state': {
            'visible': True if item['data']['meaningfulMarkers']['postponedFor'] == 1 else item['state']['visible']
        }
    }

def transition_data_between_boards(state):
    items = filter(lambda x: not x.get('state', {'checked': False })['checked'], state)

    return list(map(transition_data_in_tree_item, items))

@api_view(['POST'])
def commit_board(request, id=None):
    board = Board.objects.get(pk=id)

    new_board = Board()

    new_board.state = transition_data_between_boards(board.state)
    board.date_closed = timezone.now()

    board.save()
    new_board.save()

    return Response(BoardSerializer(new_board).data)