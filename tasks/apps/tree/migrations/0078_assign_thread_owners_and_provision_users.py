from django.conf import settings
from django.db import migrations
from django.db.models import Count

# Same owner choice as 0053_observation_user: the account that has been
# using the app on its own, falling back for dev and test databases.
OWNER_USERNAME = "dragonee"

# Frozen copy of Thread.BUILTIN_NAMES: migrations must not follow later code.
BUILTIN_THREAD_NAMES = ("Daily", "Weekly", "big-picture")


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
    """Everything that exists so far belongs to the single existing user."""
    Thread = apps.get_model("tree", "Thread")
    Breakthrough = apps.get_model("tree", "Breakthrough")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    orphan_threads = Thread.objects.filter(user__isnull=True)
    orphan_breakthroughs = Breakthrough.objects.filter(user__isnull=True)
    if not orphan_threads.exists() and not orphan_breakthroughs.exists():
        return

    owner = _owner(User)
    if owner is None:
        raise RuntimeError(
            "Threads or breakthroughs exist but there is no user to own them. "
            "Create one (manage.py createsuperuser) and run migrate again."
        )

    duplicates = sorted(
        orphan_threads.values("name")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .values_list("name", flat=True)
    )
    if duplicates:
        raise RuntimeError(
            f"Several threads share a name ({', '.join(duplicates)}); thread "
            "names become unique per user. Merge or rename them, then migrate."
        )

    orphan_threads.update(user=owner)
    orphan_breakthroughs.update(user=owner)


def provision_users(apps, schema_editor):
    """Frozen copy of services.provisioning.provision_user for every user."""
    Thread = apps.get_model("tree", "Thread")
    Board = apps.get_model("tree", "Board")
    Profile = apps.get_model("tree", "Profile")
    HabitKeyword = apps.get_model("tree", "HabitKeyword")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    for user in User.objects.order_by("pk"):
        for name in BUILTIN_THREAD_NAMES:
            thread, _ = Thread.objects.get_or_create(user=user, name=name)
            if not Board.objects.filter(thread=thread).exists():
                Board.objects.create(thread=thread)

        profile, created = Profile.objects.get_or_create(user=user)
        if created:
            # What the Profile post_save signal does at runtime.
            profile.habit_keywords.set(HabitKeyword.objects.all())


def forwards(apps, schema_editor):
    assign_owners(apps, schema_editor)
    provision_users(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0077_thread_user_breakthrough_user"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
