from django.utils import timezone


def default_title(started=None):
    """Auto-generate a trip title from its start timestamp.

    Format: ``Trip YYYY-MM-DD HH:MM`` in the server's current timezone.
    """
    moment = started or timezone.now()
    local = timezone.localtime(moment) if timezone.is_aware(moment) else moment
    return f"Trip {local.strftime('%Y-%m-%d %H:%M')}"
