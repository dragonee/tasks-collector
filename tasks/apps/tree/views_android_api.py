from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.today import (
    NoBoardError,
    add_task,
    delete_task,
    list_today_tasks,
    set_task_done,
)


def _text_from(request):
    text = request.data.get("text") if hasattr(request, "data") else None
    if text is None or not str(text).strip():
        return None
    return str(text)


def _no_board_response():
    return Response(
        {"error": "no board configured for user"},
        status=status.HTTP_409_CONFLICT,
    )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTaskListView(APIView):
    """Return today's tasks: every line in today's Plan.focus, with a
    ``done`` flag for those that also appear in today's Reflection.good.
    Unchecked items first."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            items = list_today_tasks(request.user)
        except NoBoardError:
            return _no_board_response()
        return Response(
            {"items": [{"text": it.text, "done": it.done} for it in items]},
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTaskAddView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = _text_from(request)
        if text is None:
            return Response(
                {"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            add_task(request.user, text)
        except NoBoardError:
            return _no_board_response()
        return Response({"ok": True}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTaskCompleteView(APIView):
    """Set the desired done-state of a task. ``done`` is required and is
    the target state (not a toggle)."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = _text_from(request)
        if text is None:
            return Response(
                {"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if "done" not in request.data:
            return Response(
                {"error": "done is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        done = bool(request.data.get("done"))
        try:
            set_task_done(request.user, text, done)
        except NoBoardError:
            return _no_board_response()
        return Response({"ok": True}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class AndroidTaskDeleteView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = _text_from(request)
        if text is None:
            return Response(
                {"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            delete_task(request.user, text)
        except NoBoardError:
            return _no_board_response()
        return Response({"ok": True}, status=status.HTTP_200_OK)
