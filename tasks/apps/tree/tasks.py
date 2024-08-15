from celery import shared_task

from .models import QuickNote
from django.utils import timezone
from datetime import timedelta


@shared_task
def remove_quick_notes_after(minutes=1440):
    before = timezone.now() - timedelta(minutes=minutes)

    QuickNote.objects.filter(
        published__lt=before
    ).delete()