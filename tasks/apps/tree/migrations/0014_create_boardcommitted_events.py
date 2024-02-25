# Generated by Django 3.2.16 on 2024-02-23 23:42

from django.db import migrations

from tasks.apps.tree.commit import calculate_changes_per_board
from tasks.apps.tree.models import default_state


def forwards_func(apps, schema_editor):
    BoardCommitted = apps.get_model("tree", "BoardCommitted")
    Board = apps.get_model("tree", "Board")
    Thread = apps.get_model("tree", "Thread")
    db_alias = schema_editor.connection.alias

    for board in Board.objects.using(db_alias) \
            .filter(date_closed__isnull=False) \
            .order_by('date_started'):
        
        changeset = calculate_changes_per_board(board.state)

        if None in changeset:
            after = changeset[None]
            del changeset[None]
        else:
            after = default_state()

        BoardCommitted.objects.create(
            published=board.date_closed,
            thread=board.thread,
            focus=board.focus or '',
            before=board.state,
            after=after,
            transitions=changeset,
            date_started=board.date_started,
        )

    Board.objects.using(db_alias) \
         .filter(date_closed__isnull=False) \
         .delete()

def reverse_func(apps, schema_editor):
    BoardCommitted = apps.get_model("tree", "BoardCommitted")
    Board = apps.get_model("tree", "Board")
    db_alias = schema_editor.connection.alias

    for cur in BoardCommitted.objects.using(db_alias).order_by('published'):
        Board.objects.using(db_alias).create(
            date_started=cur.date_started,
            date_closed=cur.published,
            state=cur.before,
            focus=cur.focus,
            thread=cur.thread,
        )

    BoardCommitted.objects.using(db_alias).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0013_auto_20240225_0025'),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]