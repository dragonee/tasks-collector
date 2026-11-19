from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tasks.apps.common.authentication import TokenAuthentication

from .serializers import RoleHabitSerializer
from .services.habits.roles import role_habits
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

    The most recently recorded body weight and when it was recorded (both
    null when nothing has been recorded yet), and by role what a write for it
    records: the habit's name, keyword and metrics (``roles.role_habits``),
    from which the phone builds the form of a role, such as weight.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        record = latest_weight(request.user)
        roles = {
            role: RoleHabitSerializer(habit).data
            for role, habit in role_habits(request.user).items()
        }
        return Response(
            {
                "weight_kg": record.value_kg if record else None,
                "recorded_at": record.recorded_at.isoformat() if record else None,
                "roles": roles,
            },
            status=status.HTTP_200_OK,
        )
