"""Each user's roles are filled by the habits that played them so far:
breakthrough and weight by the habits with those slugs, the phone's daily
health by the habit of the health-metrics keyword, its bike rides by the
habit of workout. The entries the sync wrote become the role's: the next day
it writes replaces its own entry of the day, not one typed by hand.

Reversing empties the roles and the marks.
"""

from django.db import migrations

BY_SLUG = {"breakthrough": "breakthrough", "weight": "weight"}
BY_KEYWORD = {"daily-health": "health-metrics", "bike-ride": "workout"}

# What the phones wrote for a role, before they said so.
WRITTEN = {"daily-health": r"^steps=\d", "bike-ride": r"Bike ride \(duration="}


def fill_roles(apps, schema_editor):
    Habit = apps.get_model("tree", "Habit")
    HabitKeyword = apps.get_model("tree", "HabitKeyword")
    HabitRole = apps.get_model("tree", "HabitRole")
    HabitTracked = apps.get_model("tree", "HabitTracked")

    for role, slug in BY_SLUG.items():
        for habit in Habit.objects.filter(slug=slug):
            HabitRole.objects.create(user_id=habit.user_id, role=role, habit=habit)

    for role, keyword in BY_KEYWORD.items():
        for found in HabitKeyword.objects.filter(keyword=keyword):
            HabitRole.objects.create(
                user_id=found.user_id, role=role, habit_id=found.habit_id
            )

    for role, pattern in WRITTEN.items():
        habits = HabitRole.objects.filter(role=role).values_list("habit_id", flat=True)
        HabitTracked.objects.filter(habit_id__in=habits, note__regex=pattern).update(
            role=role
        )


def empty_roles(apps, schema_editor):
    apps.get_model("tree", "HabitRole").objects.all().delete()
    apps.get_model("tree", "HabitTracked").objects.exclude(role="").update(role="")


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0109_habit_roles"),
    ]

    operations = [
        migrations.RunPython(fill_roles, empty_roles),
    ]
