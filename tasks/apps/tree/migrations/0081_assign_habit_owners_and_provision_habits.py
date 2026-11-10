from django.conf import settings
from django.db import migrations
from django.db.models import F, OuterRef, Subquery

# Same owner choice as 0078_assign_thread_owners_and_provision_users.
OWNER_USERNAME = "dragonee"

# Frozen copy of services.provisioning.BUILTIN_HABITS: migrations must not
# follow later code. The habits 0068 and 0074 used to create for everyone.
BUILTIN_HABITS = (
    (
        "poi",
        "POI",
        "Point of interest recorded during a Trip. "
        "Tracked via #poi/#coords/#coordinates/#latlng hashtags "
        "in journal entries; the note typically carries "
        "lat=<float> lng=<float> (and optionally acc=<float>).",
        ("poi", "coords", "coordinates", "latlng"),
    ),
    (
        "weight",
        "Weight",
        "Body weight recorded from the Health screen. "
        "Tracked via the #weight hashtag; the note carries weight=<float>kg.",
        ("weight",),
    ),
)


def _owner(User):
    for users in (
        User.objects.filter(username=OWNER_USERNAME),
        User.objects.filter(is_superuser=True),
        User.objects.all(),
    ):
        owner = users.order_by("pk").first()
        if owner is not None:
            return owner
    return None


def assign_owners(apps, schema_editor):
    """Existing habits and statistics belong to the single existing user."""
    Habit = apps.get_model("tree", "Habit")
    HabitKeyword = apps.get_model("tree", "HabitKeyword")
    HabitTracked = apps.get_model("tree", "HabitTracked")
    Statistics = apps.get_model("tree", "Statistics")
    Profile = apps.get_model("tree", "Profile")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    owner = _owner(User)
    if owner is None:
        # A fresh database: the only habits are the ones 0068 and 0074
        # seeded for everyone, so nothing can have been tracked yet. Each
        # user is given their own copies when they are created.
        if HabitTracked.objects.exists():
            raise RuntimeError(
                "Tracked habits exist but there is no user to own them. "
                "Create one (manage.py createsuperuser) and run migrate again."
            )
        HabitKeyword.objects.all().delete()
        Habit.objects.all().delete()
        # Word counts are a cache; the update_word_count command rebuilds them.
        Statistics.objects.all().delete()
        return

    Habit.objects.filter(user__isnull=True).update(user=owner)
    Statistics.objects.filter(user__isnull=True).update(user=owner)
    HabitKeyword.objects.filter(user__isnull=True).update(
        user=Subquery(Habit.objects.filter(pk=OuterRef("habit_id")).values("user"))
    )

    # Profiles used to get every keyword; keep only their own user's.
    Profile.habit_keywords.through.objects.exclude(
        habitkeyword__user=F("profile__user")
    ).delete()


def provision_habits(apps, schema_editor):
    """Frozen copy of the habit part of services.provisioning.provision_user."""
    Habit = apps.get_model("tree", "Habit")
    HabitKeyword = apps.get_model("tree", "HabitKeyword")
    Profile = apps.get_model("tree", "Profile")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    for user in User.objects.order_by("pk"):
        for slug, name, description, keywords in BUILTIN_HABITS:
            habit, _ = Habit.objects.get_or_create(
                user=user,
                slug=slug,
                defaults={"name": name, "description": description},
            )
            for keyword in keywords:
                habit_keyword, created = HabitKeyword.objects.get_or_create(
                    user=user, keyword=keyword, defaults={"habit": habit}
                )
                if created:
                    # What the HabitKeyword post_save signal does at runtime.
                    for profile in Profile.objects.filter(user=user):
                        profile.habit_keywords.add(habit_keyword)


def forwards(apps, schema_editor):
    assign_owners(apps, schema_editor)
    provision_habits(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0080_habit_keyword_statistics_user"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
