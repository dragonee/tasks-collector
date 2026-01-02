import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response as RestResponse

from .board_operations import add_task_to_board
from .commit import calculate_changes_per_board, merge
from .models import Board, BoardCommitted, Thread, default_state
from .serializers import BoardSerializer, BoardSummary


class BoardViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows boards to be viewed or edited.
    """

    def get_queryset(self):
        queryset = Board.objects.all()
        thread_id = self.request.query_params.get("thread", None)

        if thread_id is not None:
            queryset = queryset.filter(thread_id=thread_id)

        return queryset

    serializer_class = BoardSerializer


def make_board(thread_name):
    thread = Thread.objects.get(name=thread_name)

    try:
        return Board.objects.filter(thread=thread)[0]
    except IndexError:
        return Board(thread=thread)


@api_view(["POST"])
def commit_board(request, id=None):
    board = Board.objects.get(pk=id)

    changeset = calculate_changes_per_board(board.state)

    # for name, changes in changeset.items():
    #     print("Board ({})".format(name))
    #     pprint(changes)
    #     print('------------------', flush=True)

    if None in changeset:
        new_state = changeset[None]
        del changeset[None]
    else:
        new_state = default_state()

    now = timezone.now()

    BoardCommitted.objects.create(
        published=now,
        thread=board.thread,
        focus=board.focus or "",
        before=board.state,
        after=new_state,
        transitions=changeset,
        date_started=board.date_started,
    )

    other_boards = list(map(make_board, changeset.keys()))

    for other_board in other_boards:
        other_board.state = merge(other_board.state, changeset[other_board.thread.name])
        other_board.save()

    board.state = new_state
    board.date_started = now
    board.save()

    return RestResponse(BoardSerializer(board).data)


@api_view(["POST"])
def add_task(request):
    item = request.data

    # XXX hackish
    if "text" not in item or "thread-name" not in item:
        return RestResponse(
            {"errors": "no thread-name and text"}, status=status.HTTP_400_BAD_REQUEST
        )

    board = add_task_to_board(item["text"], item["thread-name"])
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


def period_from_request(request, days=7, start=None, end=None):
    from_date = request.GET.get("from", "").strip()
    to_date = request.GET.get("to", "").strip()

    if not from_date:
        from_date = start or datetime.date.today() - datetime.timedelta(days=days)

    if not to_date:
        to_date = end or datetime.date.today() + datetime.timedelta(days=1)

    return (from_date, to_date)


@login_required
def summaries(request):
    period = period_from_request(request, days=30)

    boards = BoardCommitted.objects.filter(published__range=period).order_by(
        "-published"
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
