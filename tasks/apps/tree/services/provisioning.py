"""Per-user data every account needs before the app is usable."""

from collections import namedtuple

from django.db import transaction

from ..models import Board, Habit, HabitKeyword, HabitMetric, HabitRole, Profile, Thread

BuiltinHabit = namedtuple(
    "BuiltinHabit", "slug name description keywords metrics roles"
)

# Habits the code itself records: trip points of interest (``#poi`` lines in
# trip notes and photos) and body weight from the Android Health screen
# (services.health).
BUILTIN_HABITS = (
    BuiltinHabit(
        slug="poi",
        name="POI",
        description=(
            "Point of interest recorded during a Trip. "
            "Tracked via #poi/#coords/#coordinates/#latlng hashtags "
            "in journal entries; the note typically carries "
            "lat=<float> lng=<float> (and optionally acc=<float>)."
        ),
        keywords=("poi", "coords", "coordinates", "latlng"),
        metrics=(),
        roles=(),
    ),
    BuiltinHabit(
        slug="weight",
        name="Weight",
        description=(
            "Body weight recorded from the Health screen. "
            "Tracked via the #weight hashtag; the note carries weight=<float>kg."
        ),
        keywords=("weight",),
        metrics=(
            {
                "key": "weight",
                "label": "Weight",
                "kind": HabitMetric.Kind.NUMBER,
                "unit": "kg",
                "decimals": 1,
            },
        ),
        roles=(HabitRole.Role.WEIGHT,),
    ),
)


@transaction.atomic
def provision_user(user):
    """Give ``user`` the built-in threads with a board on each, a profile and
    the built-in habits.

    Idempotent: only what is missing is created, so it is safe to run for
    existing users (see the ``provision_users`` command).
    """
    for name in Thread.BUILTIN_NAMES:
        thread, _ = Thread.objects.get_or_create(user=user, name=name)
        if not Board.objects.filter(thread=thread).exists():
            Board.objects.create(thread=thread)

    Profile.objects.get_or_create(user=user)

    for builtin in BUILTIN_HABITS:
        habit, _ = Habit.objects.get_or_create(
            user=user,
            slug=builtin.slug,
            defaults={"name": builtin.name, "description": builtin.description},
        )
        for keyword in builtin.keywords:
            # A keyword the user already gave another habit stays theirs.
            HabitKeyword.objects.get_or_create(
                user=user, keyword=keyword, defaults={"habit": habit}
            )
        for metric in builtin.metrics:
            HabitMetric.objects.get_or_create(
                habit=habit, key=metric["key"], defaults=metric
            )
        for role in builtin.roles:
            # A role the user gave another habit stays with it.
            HabitRole.objects.get_or_create(
                user=user, role=role, defaults={"habit": habit}
            )
