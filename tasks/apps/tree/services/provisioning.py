"""Per-user data every account needs before the app is usable."""

from django.db import transaction

from ..models import Board, Profile, Thread


@transaction.atomic
def provision_user(user):
    """Give ``user`` the built-in threads, a board on each and a profile.

    Idempotent: only what is missing is created, so it is safe to run for
    existing users (see the ``provision_users`` command).
    """
    for name in Thread.BUILTIN_NAMES:
        thread, _ = Thread.objects.get_or_create(user=user, name=name)
        if not Board.objects.filter(thread=thread).exists():
            Board.objects.create(thread=thread)

    Profile.objects.get_or_create(user=user)
