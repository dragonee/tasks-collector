"""What code finds a habit by: the role it fills for its user, not its slug or
its keywords, which are the user's to change (docs/design/habit-metrics.md).

A role nobody fills is filled by the first write for it: a habit made from
the role, with its metrics and the keywords nobody has.
"""

from collections import namedtuple

from django.db import IntegrityError, transaction
from django.utils.text import slugify

from ...models import Habit, HabitKeyword, HabitMetric, HabitRole

Role = HabitRole.Role

RoleSpec = namedtuple("RoleSpec", "name keywords metrics one_per_day")


def _metric(key, label, kind=HabitMetric.Kind.NUMBER, unit="", decimals=0):
    return {
        "key": key,
        "label": label,
        "kind": kind,
        "unit": unit,
        "decimals": decimals,
    }


ROLES = {
    Role.BREAKTHROUGH: RoleSpec("Breakthrough", ("breakthrough",), (), False),
    Role.WEIGHT: RoleSpec(
        "Weight",
        ("weight",),
        (_metric("weight", "Weight", unit="kg", decimals=1),),
        False,
    ),
    Role.DAILY_HEALTH: RoleSpec(
        "Health",
        ("health-metrics",),
        (
            _metric("steps", "Steps"),
            _metric("distance", "Distance", unit="km", decimals=1),
            _metric("active", "Active", unit="min"),
            _metric("kcal", "Calories"),
        ),
        True,
    ),
    Role.BIKE_RIDE: RoleSpec(
        "Workout",
        ("workout",),
        (_metric("duration", "Duration", kind=HabitMetric.Kind.DURATION),),
        False,
    ),
}


def habit_for(user, role):
    """The habit that fills ``role`` for ``user``, or None."""
    return Habit.objects.filter(roles__user=user, roles__role=role).first()


RoleHabit = namedtuple("RoleHabit", "name keyword metrics")


def role_habits(user):
    """By role, what a write for it records for ``user``: the name, the
    keyword (the role's own when the habit has it) and the metrics of the
    habit that fills it. For a role nobody fills, those of the habit its first
    write makes, so that a phone can always ask for a role's values."""
    filled = {
        row.role: row.habit
        for row in HabitRole.objects.filter(user=user)
        .select_related("habit")
        .prefetch_related("habit__keywords", "habit__metrics")
    }
    habits = {}
    for role, spec in ROLES.items():
        habit = filled.get(role)
        if habit is None:
            free = [
                keyword
                for keyword in spec.keywords
                if not HabitKeyword.objects.filter(user=user, keyword=keyword).exists()
            ]
            metrics = [HabitMetric(**metric) for metric in spec.metrics]
            habits[role] = RoleHabit(spec.name, next(iter(free), ""), metrics)
            continue
        keywords = [keyword.keyword for keyword in habit.keywords.all()]
        own = [keyword for keyword in spec.keywords if keyword in keywords]
        habits[role] = RoleHabit(
            habit.name, next(iter(own + keywords), ""), list(habit.metrics.all())
        )
    return habits


def roles_of(habit):
    """The roles ``habit`` fills."""
    return list(habit.roles.values_list("role", flat=True))


def one_per_day_role(habit, keyword):
    """The role of one entry a day that a write by ``keyword`` to ``habit``
    is for: the one ``habit`` fills whose own keyword it is (what a phone sent
    before it said the role), or ""."""
    roles = set(roles_of(habit))
    return next(
        (
            role
            for role, spec in ROLES.items()
            if spec.one_per_day and role in roles and keyword in spec.keywords
        ),
        "",
    )


def declare(habit, role):
    """Give ``habit`` the metrics ``role`` writes that it doesn't record yet."""
    for metric in ROLES[role].metrics:
        HabitMetric.objects.get_or_create(
            habit=habit, key=metric["key"], defaults=metric
        )


def fill(role, habit):
    """Make ``habit`` the one that fills ``role`` for its user."""
    HabitRole.objects.update_or_create(
        user=habit.user, role=role, defaults={"habit": habit}
    )
    declare(habit, role)


def habit_for_writing(user, role):
    """The habit that fills ``role`` for ``user``. When none does, a new one
    made from the role fills it from then on: its name (with a number when the
    user has a habit of that slug), its metrics, its keywords nobody has."""
    habit = habit_for(user, role)
    if habit is None:
        try:
            with transaction.atomic():
                habit = _made(user, role)
        except IntegrityError:
            # Another write for the role made one at the same moment.
            habit = habit_for(user, role)
            if habit is None:
                raise
    declare(habit, role)
    return habit


def _made(user, role):
    spec = ROLES[role]
    base = slugify(spec.name)
    slug, number = base, 1
    while Habit.objects.filter(user=user, slug=slug).exists():
        number += 1
        slug = f"{base}-{number}"
    habit = Habit.objects.create(user=user, name=spec.name, slug=slug)
    for keyword in spec.keywords:
        if not HabitKeyword.objects.filter(user=user, keyword=keyword).exists():
            HabitKeyword.objects.create(habit=habit, keyword=keyword)
    HabitRole.objects.create(user=user, role=role, habit=habit)
    return habit
