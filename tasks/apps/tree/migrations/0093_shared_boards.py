from django.db import migrations, models
from django.db.models import F

BUILTIN_THREAD_NAMES = ("Daily", "Weekly", "big-picture")


def share_default_boards_of_other_users(apps, schema_editor):
    """A profile whose default board is another user's thread has used that
    board since before threads had owners: a joint board. Make it a share:
    the profile's user becomes an editor of that board.

    Built-in boards (Daily, Weekly, big-picture) can't be shared, so a
    profile pointing at someone else's is cleared and falls back to the
    user's own Daily.
    """
    Profile = apps.get_model("tree", "Profile")
    EventStreamAccess = apps.get_model("tree", "EventStreamAccess")

    profiles = (
        Profile.objects.exclude(default_board_thread=None)
        .exclude(default_board_thread__user=F("user"))
        .select_related("default_board_thread")
    )
    for profile in profiles:
        thread = profile.default_board_thread
        if thread.name in BUILTIN_THREAD_NAMES:
            profile.default_board_thread = None
            profile.save(update_fields=["default_board_thread"])
            continue
        EventStreamAccess.objects.get_or_create(
            stream_id=thread.board_stream_id,
            user_id=profile.user_id,
            defaults={"role": "editor"},
        )


def remove_editors(apps, schema_editor):
    """The previous release has no editor role. Cleared default boards are
    not restored."""
    EventStreamAccess = apps.get_model("tree", "EventStreamAccess")
    EventStreamAccess.objects.filter(role="editor").delete()


class Migration(migrations.Migration):
    """Boards can be shared with edit access."""

    dependencies = [
        ("tree", "0092_event_created_by_required"),
    ]

    operations = [
        migrations.AlterField(
            model_name="eventstreamaccess",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Owner"),
                    ("editor", "Editor"),
                    ("viewer", "Viewer"),
                ],
                max_length=16,
            ),
        ),
        migrations.RunPython(share_default_boards_of_other_users, remove_editors),
    ]
