from django.utils import timezone

from datetime import datetime

def aware_from_date(d):
    return timezone.make_aware(datetime.combine(d, datetime.min.time()))