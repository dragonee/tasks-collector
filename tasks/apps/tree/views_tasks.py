"""Tasks by id: what is planned, and what can be done with it.

For clients that know which task they mean. Every date comes from the client:
the server's day is a different one for part of every night.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Board, Task, Thread
from .services.tasks import agenda, documents
from .services.tasks import operations as tasks
from .services.today import operations as today
from .services.trips.operations import StoryNotFoundError, StoryStoppedError

AGENDA_PLANS = (
    ("daily", Thread.DAILY),
    ("weekly", Thread.WEEKLY),
    ("monthly", Thread.BIG_PICTURE),
)


class DaySerializer(serializers.Serializer):
    date = serializers.DateField()


class PlanRefSerializer(serializers.Serializer):
    """One of the caller's plans: the one of ``thread`` that the day ``date``
    falls in."""

    thread = serializers.ChoiceField(choices=Thread.BUILTIN_NAMES, default=Thread.DAILY)
    date = serializers.DateField()


class CreateSerializer(PlanRefSerializer):
    """What to plan: something typed (``text``), or a board item."""

    text = serializers.CharField(required=False, trim_whitespace=True)
    board_id = serializers.IntegerField(required=False)
    item_id = serializers.CharField(required=False)

    def validate(self, data):
        item = "board_id" in data and "item_id" in data
        if bool(data.get("text")) == item:
            raise serializers.ValidationError(
                "Give either text, or board_id and item_id."
            )
        return data


class RenameSerializer(serializers.Serializer):
    text = serializers.CharField(trim_whitespace=True)

    def validate_text(self, text):
        if "\n" in text or "\r" in text:
            raise serializers.ValidationError("A task is one line.")
        return text


class MoveSerializer(serializers.Serializer):
    thread = serializers.ChoiceField(choices=Thread.BUILTIN_NAMES, default=Thread.DAILY)
    from_date = serializers.DateField()
    to_date = serializers.DateField()


class CompleteSerializer(serializers.Serializer):
    # The day it was done on for the caller, and the moment (now if left out).
    day = serializers.DateField()
    at = serializers.DateTimeField(required=False)
    mark = serializers.ChoiceField(
        choices=("~", "^"), required=False, allow_null=True, default=None
    )
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    story_id = serializers.IntegerField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(
        required=False, allow_null=True, max_length=64
    )


class ReopenSerializer(serializers.Serializer):
    # How many steps the caller saw done; see ``tasks.reopen``.
    done_count = serializers.IntegerField(required=False, allow_null=True, min_value=1)


def _valid(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _task(request, task_id):
    """A task the caller may change, or a 404."""
    return get_object_or_404(Task.objects.editable_by(request.user), pk=task_id)


def _plan(user, thread_name, day, create=False):
    thread = get_object_or_404(Thread, user=user, name=thread_name)
    return documents.plan_for(
        thread, agenda.period_end(thread_name, day), create=create
    )


def _described(task, user):
    return agenda.describe([agenda.task_shown(task, user)], user)[0]


@api_view(["GET"])
def task_agenda(request):
    """What the caller has planned around ``date``: the plan of the day, of
    its week and of its month, each task with whether it is done."""
    day = _valid(DaySerializer, request.query_params)["date"]

    body = {"date": day}
    for key, thread_name in AGENDA_PLANS:
        pub_date = agenda.period_end(thread_name, day)
        shown = agenda.plan_tasks(request.user, pub_date, thread_name)
        body[key] = {
            "thread": thread_name,
            "pub_date": pub_date,
            "tasks": agenda.describe(shown, request.user),
        }
    return Response(body)


@api_view(["POST"])
def task_create(request):
    """Plan something on one of the caller's plans, and return its task.

    ``text`` plans what was typed: the task of that text if the caller has it
    planned already (on that plan, for the week or the month, on a recent
    day), else a new one. ``board_id`` and ``item_id`` plan a board item.
    """
    data = _valid(CreateSerializer, request.data)
    pub_date = agenda.period_end(data["thread"], data["date"])

    try:
        if "item_id" in data:
            task = today.plan_item(
                request.user,
                data["board_id"],
                data["item_id"],
                data["thread"],
                pub_date,
            )
        else:
            task = today.plan_text(
                request.user, data["text"], data["thread"], pub_date, data["date"]
            )
    except Board.DoesNotExist, LookupError:
        return Response(
            {"error": "no such board item"}, status=status.HTTP_404_NOT_FOUND
        )

    return Response(_described(task, request.user), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
def task_detail(request, task_id):
    """A task; PATCH ``text`` renames it, on every plan and on its board."""
    task = _task(request, task_id)

    if request.method == "PATCH":
        text = _valid(RenameSerializer, request.data)["text"]
        with transaction.atomic():
            today.lock_day(request.user)
            task = tasks.rename(task, text)

    return Response(_described(task, request.user))


@api_view(["POST"])
@transaction.atomic
def task_plan(request, task_id):
    """Put the task on another of the caller's plans as well."""
    task = _task(request, task_id)
    data = _valid(PlanRefSerializer, request.data)

    today.lock_day(request.user)
    tasks.plan(task, _plan(request.user, data["thread"], data["date"], create=True))

    return Response(_described(task, request.user))


@api_view(["POST"])
@transaction.atomic
def task_unplan(request, task_id):
    """Take the task off one of the caller's plans. 204 when that was the
    last thing that remembered it and the task is gone."""
    task = _task(request, task_id)
    data = _valid(PlanRefSerializer, request.data)

    today.lock_day(request.user)
    plan = _plan(request.user, data["thread"], data["date"])
    if plan is not None:
        tasks.unplan(task, plan)

    if not Task.objects.filter(pk=task_id).exists():
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response(_described(task, request.user))


@api_view(["POST"])
@transaction.atomic
def task_move(request, task_id):
    """Move the task from one of the caller's plans to another of the same
    thread: to tomorrow, to next week."""
    task = _task(request, task_id)
    data = _valid(MoveSerializer, request.data)

    today.lock_day(request.user)
    to_plan = _plan(request.user, data["thread"], data["to_date"], create=True)
    from_plan = _plan(request.user, data["thread"], data["from_date"])
    if from_plan is None or from_plan == to_plan:
        tasks.plan(task, to_plan)
    else:
        tasks.move(task, from_plan, to_plan)

    return Response(_described(task, request.user))


@api_view(["POST"])
def task_complete(request, task_id):
    """Do a step of the task: the whole of it, or the next counted step.

    A ``note``, or a ``story_id`` (save to trip), makes a journal entry. The
    same ``idempotency_key`` sent again does nothing more.
    """
    task = _task(request, task_id)
    data = _valid(CompleteSerializer, request.data)

    try:
        with transaction.atomic():
            today.lock_day(request.user)
            story = None
            if data.get("story_id") is not None:
                story = today.owned_active_story(request.user, data["story_id"])
            tasks.complete(
                task,
                request.user,
                day=data["day"],
                at=data.get("at") or timezone.now(),
                mark=data["mark"],
                note=data.get("note"),
                story=story,
                idempotency_key=data.get("idempotency_key"),
            )
    except StoryNotFoundError:
        return Response({"error": "story not found"}, status=status.HTTP_404_NOT_FOUND)
    except StoryStoppedError:
        return Response(
            {"error": "trip is stopped; cannot add notes"},
            status=status.HTTP_409_CONFLICT,
        )

    task.refresh_from_db()
    return Response(_described(task, request.user))


@api_view(["POST"])
@transaction.atomic
def task_reopen(request, task_id):
    """Take back the last step done on the task. With ``done_count`` (how
    many steps the caller saw done) only while the task has that many: the
    same request sent again takes nothing more back."""
    task = _task(request, task_id)
    data = _valid(ReopenSerializer, request.data)

    today.lock_day(request.user)
    tasks.reopen(task, done_count=data.get("done_count"))

    task.refresh_from_db()
    return Response(_described(task, request.user))
