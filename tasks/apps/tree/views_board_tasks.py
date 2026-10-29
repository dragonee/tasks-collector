import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response as RestResponse

from .board_operations import (
    UnknownThreadError,
    add_task_to_board,
    close_board,
    current_board_thread_name,
)
from .models import Board, BoardCommitted
from .serializers import BoardSerializer, BoardSummary


class BoardFilter(filters.FilterSet):
    thread = filters.NumberFilter(field_name="thread_id")

    class Meta:
        model = Board
        fields = ["thread"]


class BoardViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """

    queryset = Board.objects.all()

    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = BoardFilter

    serializer_class = BoardSerializer

    # No create or delete. The serializer can't set a thread, so a POSTed
    # board is an orphan no thread lists and the commit can't record. A
    # DELETE would erase a board without the guard below. Boards come from
    # the admin or from a commit moving items to a thread with no board.
    http_method_names = ["get", "put", "patch", "head", "options"]

    def update(self, request, *args, **kwargs):
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


@api_view(["POST"])
def commit_board(request, id=None):
    board = get_object_or_404(Board, pk=id)

    try:
        board = close_board(board)
    except UnknownThreadError as e:
        return RestResponse({"errors": str(e)}, status=status.HTTP_409_CONFLICT)

    return RestResponse(BoardSerializer(board).data)


@api_view(["POST"])
def add_task(request):
    item = request.data

    text = item.get("text")
    if not text:
        return RestResponse({"errors": "no text"}, status=status.HTTP_400_BAD_REQUEST)

    # thread-name is optional: when omitted, append to the caller's current
    # board — Profile.default_board_thread, or Daily as a fallback — which is
    # the same board the Android picker shows. Explicit callers (e.g. the CLI's
    # "text > Thread" syntax) keep naming the thread directly.
    thread_name = item.get("thread-name") or current_board_thread_name(request.user)

    board = add_task_to_board(text, thread_name)
    if board is None:
        return RestResponse(
            {"errors": f"no board for thread {thread_name!r}"},
            status=status.HTTP_409_CONFLICT,
        )
    return RestResponse(BoardSerializer(board).data)


@login_required
def board_summary(request, id):
    board = get_object_or_404(BoardCommitted, pk=id)

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

    boards = (
        BoardCommitted.objects.filter(published__date__range=period)
        .select_related("thread")
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
