from datetime import timedelta

from django.utils import timezone

from celery import shared_task

from .models import QuickNote


@shared_task
def remove_quick_notes_after(**kwargs):
    before = timezone.now() - timedelta(**kwargs)

    QuickNote.objects.filter(published__lt=before).delete()
