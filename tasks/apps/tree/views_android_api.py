from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.health import latest_weight
from .services.today import NoBoardError, list_board_items


def _no_board_response():
    return Response(
        {"error": "no board configured for user"},
        status=status.HTTP_409_CONFLICT,
    )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidBoardListView(APIView):
    """Return the user's current board flattened to a depth-annotated list:
    every item in pre-order, with its MoSCoW marker, done flag, id and board,
    and whether it is planned (has a task). Source for the Android 'add from
    board' picker. The board is date-independent, so no ``date`` parameter is
    required.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            items = list_board_items(request.user)
        except NoBoardError:
            return _no_board_response()
        return Response(
            {
                "items": [
                    {
                        "text": it.text,
                        "moscow": it.moscow,
                        "depth": it.depth,
                        "done": it.done,
                        "id": it.id,
                        "board_id": it.board_id,
                        "planned": it.planned,
                    }
                    for it in items
                ]
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidHealthDataView(APIView):
    """Return server-side health data for the Health screen.

    Currently just the most recently recorded body weight and when it was
    recorded; both null when nothing has been recorded yet. Named generically
    so other server-derived metrics can be added here later.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        record = latest_weight(request.user)
        if record is None:
            return Response(
                {"weight_kg": None, "recorded_at": None},
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "weight_kg": record.value_kg,
                "recorded_at": record.recorded_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )
