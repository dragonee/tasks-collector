import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tasks.apps.common.authentication import TokenAuthentication

from .models import HabitTracked, Thread
from .serializers import (
    HabitTrackedSerializer,
    TrackedHabitSerializer,
    TrackHabitAPISerializer,
)
from .services.habits.metrics import write
from .services.habits.roles import ROLES, one_per_day_role
from .services.habits.tracking import track
from .services.idempotency import existing_event


def _aware_midday(date: datetime.date):
    return timezone.make_aware(datetime.datetime.combine(date, datetime.time(12, 0)))


@method_decorator(csrf_exempt, name="dispatch")
class TrackHabitAPIView(APIView):
    """JSON endpoint for mobile clients to record a habit's entry of a day.

    The habit is the one a ``keyword`` names (the same hashtag the user would
    type in the journal) or the one that fills a ``role``, made when none
    does. ``values`` of its metrics, by key, are written into the note.

    One entry a day: a second POST for the same day updates the entry rather
    than adding one. For a role of one entry a day (the phone's daily health)
    that is the role's own entry, never one typed by hand; the role's own
    keyword (health-metrics, from phones before they said the role) counts as
    the role. Any other write replaces the day's entry that is no role's.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TrackHabitAPISerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        habit = data["habit"]
        role = data["role"] or one_per_day_role(habit, data.get("keyword"))
        note = write(data["note"], habit.metrics.all(), data["values"])
        thread = Thread.objects.daily(request.user)
        published = _aware_midday(data["date"])

        same_day = HabitTracked.objects.filter(
            habit=habit, published__date=data["date"]
        )
        if role and ROLES[role].one_per_day:
            same_day = same_day.filter(role=role)
        else:
            same_day = same_day.filter(role="")
        existing = same_day.first()

        if existing is not None:
            existing.note = note
            existing.occured = True
            existing.thread = thread
            existing.published = published
            existing.role = role
            existing.save()
        else:
            HabitTracked.objects.create(
                habit=habit,
                occured=True,
                note=note,
                thread=thread,
                published=published,
                created_by=request.user,
                role=role,
            )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class TrackedHabitCreateView(APIView):
    """POST api/v1/habit/tracked/: a new entry, each time, of the habit a
    ``keyword`` names or a ``role`` is filled by (made when none is), with its
    metrics' ``values`` (by key) written into the note.

    Sent again with the same ``idempotency_key``, it gives back the entry the
    first one made (200) and makes nothing more.
    """

    def post(self, request):
        serializer = TrackedHabitSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        key = data.get("idempotency_key")

        existing = existing_event(HabitTracked, request.user, key)
        if existing is None:
            try:
                with transaction.atomic():
                    entry = track(
                        request.user,
                        data["habit"],
                        note=data["note"],
                        values=data["values"],
                        published=data.get("published"),
                        occured=data["occured"],
                        idempotency_key=key,
                        role=data["role"],
                    )
            except IntegrityError:
                # The same key, sent twice at once: the other one made it.
                existing = existing_event(HabitTracked, request.user, key)
                if existing is None:
                    raise
            else:
                return Response(
                    HabitTrackedSerializer(entry, context={"request": request}).data,
                    status=status.HTTP_201_CREATED,
                )

        return Response(
            HabitTrackedSerializer(existing, context={"request": request}).data
        )
