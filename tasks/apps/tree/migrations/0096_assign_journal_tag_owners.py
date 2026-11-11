from django.conf import settings
from django.db import migrations

# Same owner choice as 0078_assign_thread_owners_and_provision_users.
OWNER_USERNAME = "dragonee"


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


def forwards(apps, schema_editor):
    """Every user who tagged an entry with a tag gets a tag of their own.

    The tag itself goes to the owner when they used it (or when nobody did),
    otherwise to the first user who did; everyone else who used it gets a
    copy with the same name and slug, and their entries are moved to it.
    """
    JournalTag = apps.get_model("tree", "JournalTag")
    Tagging = JournalTag.journals.through
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    owner = _owner(User)

    for tag in JournalTag.objects.filter(user__isnull=True).order_by("pk"):
        users = sorted(
            set(
                Tagging.objects.filter(journaltag=tag).values_list(
                    "journaladded__thread__user", flat=True
                )
            )
        )

        if not users:
            if owner is None:
                # A fresh database: nobody to own it, and nothing tagged.
                tag.delete()
                continue
            keeper = owner.pk
        elif owner is not None and owner.pk in users:
            keeper = owner.pk
        else:
            keeper = users[0]

        tag.user_id = keeper
        tag.save(update_fields=["user"])

        for user_id in users:
            if user_id == keeper:
                continue
            copy = JournalTag.objects.create(
                user_id=user_id, name=tag.name, slug=tag.slug
            )
            Tagging.objects.filter(
                journaltag=tag, journaladded__thread__user=user_id
            ).update(journaltag=copy)


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0095_journaltag_user"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
