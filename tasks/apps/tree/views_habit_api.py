import datetime

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import HabitKeyword, HabitTracked, Thread
from .serializers import TrackHabitAPISerializer


def _aware_midday(date: datetime.date):
    return timezone.make_aware(datetime.datetime.combine(date, datetime.time(12, 0)))


@method_decorator(csrf_exempt, name="dispatch")
class TrackHabitAPIView(APIView):
    """JSON endpoint for mobile clients to record a HabitTracked event.

    Resolves the target Habit by HabitKeyword text (the same hashtag the user
    would type in the journal), so the mobile contract doesn't depend on the
    Habit table's slug column.

    Idempotent on (habit, date): a second POST for the same day updates the
    existing event's note rather than inserting a duplicate.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TrackHabitAPISerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        keyword = get_object_or_404(
            HabitKeyword.objects.select_related("habit"), keyword=data["keyword"]
        )
        habit = keyword.habit
        thread = get_object_or_404(Thread, name="Daily")

        published = _aware_midday(data["date"])

        existing = HabitTracked.objects.filter(
            habit=habit, published__date=data["date"]
        ).first()

        if existing is not None:
            existing.note = data["note"]
            existing.occured = True
            existing.thread = thread
            existing.published = published
            existing.save()
        else:
            HabitTracked.objects.create(
                habit=habit,
                occured=True,
                note=data["note"],
                thread=thread,
                published=published,
            )

        return Response({"ok": True}, status=status.HTTP_200_OK)
