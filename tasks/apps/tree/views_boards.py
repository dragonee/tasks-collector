import datetime

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, render

from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response as RestResponse

from .board_operations import (
    UnknownThreadError,
    add_unscheduled_task,
    close_board,
    current_board_thread_name,
)
from .models import Board, BoardCommitted
from .serializers import BoardSerializer, BoardSummary
from .services.tasks import board_links


class BoardFilter(filters.FilterSet):
    thread = filters.NumberFilter(field_name="thread_id")

    class Meta:
        model = Board
        fields = ["thread"]


class BoardViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """

    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = BoardFilter

    serializer_class = BoardSerializer

    # No create or delete. The serializer can't set a thread, so a POSTed
    # board is an orphan no thread lists and the commit can't record. A
    # DELETE would erase a board without the guard below. Boards come from
    # the admin or from a commit moving items to a thread with no board.
    http_method_names = ["get", "put", "patch", "head", "options"]

    def get_queryset(self):
        # The user's boards and the boards shared with them to edit.
        return Board.objects.editable_by(self.request.user).select_related(
            "thread__user"
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        # Whoever writes a board takes its row first (see services.tasks):
        # the tree is saved whole, and a task completed meanwhile ticks an
        # item of it.
        list(Board.objects.select_for_update().filter(pk=kwargs.get("pk")))

        # A stale or broken client (e.g. a tree view that serialized an empty
        # model) can PUT `state: []` and silently erase the whole board. An
        # empty state is only plausible when the board is already down to its
        # last item — reject the rest as wipes. Clearing a board on purpose
        # goes through /boards/<id>/commit/, which bypasses this endpoint.
        new_state = request.data.get("state")
        current_state = self.get_object().state or []

        if new_state == [] and len(current_state) > 1:
            return RestResponse(
                {
                    "errors": "refusing to erase a non-empty board; "
                    "use the commit endpoint to clear it"
                },
                status=status.HTTP_409_CONFLICT,
            )

        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        # The tree comes from a browser that may have loaded it before an
        # item was planned: which task an item has is the server's to say.
        board = serializer.save()
        if board_links.reapply(board):
            board.save()


@api_view(["POST"])
def commit_board(request, id=None):
    board = get_object_or_404(Board.objects.editable_by(request.user), pk=id)

    try:
        board = close_board(board, created_by=request.user)
    except UnknownThreadError as e:
        return RestResponse({"errors": str(e)}, status=status.HTTP_409_CONFLICT)

    return RestResponse(BoardSerializer(board, context={"request": request}).data)


@api_view(["POST"])
def append_unscheduled_task(request):
    item = request.data

    text = item.get("text")
    if not text:
        return RestResponse({"errors": "no text"}, status=status.HTTP_400_BAD_REQUEST)

    # thread-name is optional: when omitted, append to the caller's current
    # board — Profile.default_board_thread, or Daily as a fallback — which is
    # the same board the Android picker shows. Explicit callers (e.g. the CLI's
    # "text > Thread" syntax) keep naming the thread directly; a board shared
    # with the caller can be named too.
    thread_name = item.get("thread-name") or None

    board = add_unscheduled_task(request.user, text, thread_name)
    if board is None:
        name = thread_name or current_board_thread_name(request.user)
        return RestResponse(
            {"errors": f"no board for thread {name!r}"},
            status=status.HTTP_409_CONFLICT,
        )
    return RestResponse(BoardSerializer(board, context={"request": request}).data)


@login_required
def board_summary(request, id):
    board = get_object_or_404(
        BoardCommitted.objects.visible_to(request.user).select_related(
            "thread__user", "created_by"
        ),
        pk=id,
    )

    summary = BoardSummary(board)

    return render(
        request,
        "summary.html",
        {
            "boards": [board],
            "summaries": [summary],
            "single_view": True,
        },
    )


def _date_param(request, name):
    """The ``name`` query param as a date, or None when missing or malformed."""
    try:
        return datetime.date.fromisoformat(request.GET.get(name, "").strip())
    except ValueError:
        return None


def period_from_request(request, days=7):
    """The ``(from, to)`` dates from the query params, both days inclusive.
    A missing or malformed date falls back to the last ``days`` days up to
    today."""
    today = datetime.date.today()

    from_date = _date_param(request, "from") or today - datetime.timedelta(days=days)
    to_date = _date_param(request, "to") or today

    return (from_date, to_date)


@login_required
def summaries(request):
    period = period_from_request(request, days=30)

    # Commits on the user's boards and on the boards shared with them, by
    # whoever committed them.
    boards = (
        BoardCommitted.objects.visible_to(request.user)
        .filter(published__date__range=period)
        .select_related("thread__user", "created_by")
        .order_by("-published")
    )

    summaries = [BoardSummary(board) for board in boards]

    return render(
        request,
        "summary.html",
        {
            "boards": boards,
            "summaries": summaries,
            "single_view": False,
        },
    )
