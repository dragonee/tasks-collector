import datetime
import re
import secrets
from calendar import monthrange

from django.conf import settings
from django.db import migrations
from django.utils import timezone

BUILTIN = ("Daily", "Weekly", "big-picture")
WRITE_ROLES = ("owner", "editor")
REFLECTION_FIELDS = ("good", "better", "best")

# As services.progress when this migration was written.
PROGRESS_RE = re.compile(r"\((\d+)(?:/(\d+))?\)")


def _split(text):
    if not text:
        return []
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _progress(text):
    """(span, first number, total) of the step counter in ``text``, or None."""
    match = PROGRESS_RE.search(text or "")
    if match is None:
        return None
    first, second = int(match.group(1)), match.group(2)
    total = first if second is None else int(second)
    if total < 1:
        return None
    return match.span(), first, total


def _base(text):
    progress = _progress(text)
    if progress is None:
        return (text or "").strip()
    (start, end), _first, _total = progress
    return (text[:start].rstrip() + " " + text[end:].lstrip()).strip()


def _walk(items):
    for item in items or []:
        yield item
        yield from _walk(item.get("children"))


def _period(thread_name, pub_date):
    """First and last day of the period a plan dated ``pub_date`` covers."""
    if thread_name == "Weekly":
        return pub_date - datetime.timedelta(days=pub_date.weekday()), pub_date
    if thread_name == "big-picture":
        last = monthrange(pub_date.year, pub_date.month)[1]
        return pub_date.replace(day=1), pub_date.replace(day=last)
    return pub_date, pub_date


def _make_lines(apps):
    """A row for every line of every plan and reflection, saying what the
    text columns say. The columns are left as they are."""
    Plan = apps.get_model("tree", "Plan")
    PlanLine = apps.get_model("tree", "PlanLine")
    Reflection = apps.get_model("tree", "Reflection")
    ReflectionLine = apps.get_model("tree", "ReflectionLine")

    PlanLine.objects.bulk_create(
        PlanLine(plan_id=plan_id, position=position, text=text)
        for plan_id, focus in Plan.objects.values_list("pk", "focus")
        for position, text in enumerate(_split(focus))
    )
    ReflectionLine.objects.bulk_create(
        ReflectionLine(
            reflection_id=row["pk"], field=field, position=position, text=text
        )
        for row in Reflection.objects.values("pk", *REFLECTION_FIELDS)
        for field in REFLECTION_FIELDS
        for position, text in enumerate(_split(row[field]))
    )


def _default_board_thread(apps, user_id, daily):
    """As board_operations.board_thread_for."""
    Profile = apps.get_model("tree", "Profile")
    EventStreamAccess = apps.get_model("tree", "EventStreamAccess")

    profile = Profile.objects.filter(user_id=user_id).first()
    thread = profile.default_board_thread if profile is not None else None
    if (
        thread is not None
        and EventStreamAccess.objects.filter(
            stream_id=thread.board_stream_id, user_id=user_id, role__in=WRITE_ROLES
        ).exists()
    ):
        return thread
    return daily


def _board_items_by_text(apps, user_id):
    """text -> [(board, item)] over the latest board of every thread whose
    board the user may change."""
    Board = apps.get_model("tree", "Board")

    latest = {}
    boards = Board.objects.filter(
        thread__board_stream__access__user_id=user_id,
        thread__board_stream__access__role__in=WRITE_ROLES,
    ).order_by("thread_id", "-date_started")
    for board in boards:
        latest.setdefault(board.thread_id, board)

    by_text = {}
    for board in latest.values():
        for item in _walk(board.state):
            data = item.get("data") or {}
            text = data.get("text", item.get("text"))
            if text and not data.get("taskId") and item.get("id"):
                by_text.setdefault(text, []).append((board, item))
    return by_text


def _make_tasks(apps):
    """The lines of the plans whose period is not over become tasks: the
    Daily plans from yesterday on, the Weekly plan of this week and the
    big-picture plan of this month, and later ones.

    The same text on several of a user's plans is one task. It is as done as
    the reflections of those periods say; the lines that say so become the
    task's. It is linked to the one board item of that text, if there is
    exactly one.
    """
    Thread = apps.get_model("tree", "Thread")
    Plan = apps.get_model("tree", "Plan")
    PlanLine = apps.get_model("tree", "PlanLine")
    ReflectionLine = apps.get_model("tree", "ReflectionLine")
    Task = apps.get_model("tree", "Task")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    today = datetime.date.today()
    now = timezone.now()
    opens = {
        "Daily": today - datetime.timedelta(days=1),
        "Weekly": today,
        "big-picture": today,
    }
    anchors = set()

    for user_id in User.objects.values_list("pk", flat=True).order_by("pk"):
        threads = {
            thread.name: thread
            for thread in Thread.objects.filter(user_id=user_id, name__in=BUILTIN)
        }
        if "Daily" not in threads:
            continue

        stream_id = _default_board_thread(
            apps, user_id, threads["Daily"]
        ).board_stream_id

        plans = [
            plan
            for name in BUILTIN
            if name in threads
            for plan in Plan.objects.filter(
                thread=threads[name], pub_date__gte=opens[name]
            ).order_by("pub_date")
        ]

        tasks = {}
        periods = {}
        for plan in plans:
            name = next(n for n, thread in threads.items() if thread.pk == plan.thread_id)
            taken = set()
            for line in PlanLine.objects.filter(plan=plan).order_by("position"):
                text = line.text
                if not any(character.isalnum() for character in text):
                    continue
                if text in taken:
                    # Twice on one plan: the second stays a plain line.
                    continue
                taken.add(text)

                task = tasks.get(text)
                if task is None:
                    anchor = secrets.token_hex(4)
                    while anchor in anchors:
                        anchor = secrets.token_hex(4)
                    anchors.add(anchor)
                    task = tasks[text] = Task.objects.create(
                        user_id=user_id,
                        text=text,
                        anchor=anchor,
                        event_stream_id=stream_id,
                    )
                periods.setdefault(text, []).append((plan, _period(name, plan.pub_date)))

                line.task = task
                line.text = ""
                line.save(update_fields=["task", "text"])

        if not tasks:
            continue

        items = _board_items_by_text(apps, user_id)
        changed_boards = {}

        for text, task in tasks.items():
            counted = _progress(text)
            steps = 0
            for plan, (first, last) in periods[text]:
                lines = ReflectionLine.objects.filter(
                    task__isnull=True,
                    reflection__pub_date__range=(first, last),
                ).filter(
                    # The plan's own reflection, and the Daily ones of its days.
                    reflection__thread_id__in={plan.thread_id, threads["Daily"].pk},
                )
                for line in lines:
                    if counted is None:
                        if line.text != text:
                            continue
                        steps = max(steps, 1)
                    else:
                        value = _progress(line.text)
                        if value is None or _base(line.text) != _base(text):
                            continue
                        steps = max(steps, value[1])
                    line.task = task
                    line.save(update_fields=["task"])

            total = counted[2] if counted is not None else 1
            task.done_count = steps
            if steps >= total:
                task.completed_at = now

            matches = items.get(text, [])
            if len(matches) == 1:
                board, item = matches[0]
                item.setdefault("data", {})["taskId"] = str(task.pk)
                task.board = board
                task.board_item_id = item["id"]
                task.event_stream_id = board.thread.board_stream_id
                changed_boards[board.pk] = board

            task.save()

        for board in changed_boards.values():
            board.save(update_fields=["state"])


def forwards(apps, schema_editor):
    _make_lines(apps)
    _make_tasks(apps)


def backwards(apps, schema_editor):
    """The rows go with their tables (0100). What would be left of the tasks
    is the link each board item has to one, and the events of completions
    made since (their rows in the table all events share). The text columns
    were never changed."""
    Board = apps.get_model("tree", "Board")

    apps.get_model("tree", "TaskCompleted").objects.all().delete()

    for board in Board.objects.all():
        changed = False
        for item in _walk(board.state if isinstance(board.state, list) else []):
            data = item.get("data")
            if isinstance(data, dict) and data.get("taskId"):
                data["taskId"] = None
                changed = True
        if changed:
            board.save(update_fields=["state"])


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0100_tasks"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=backwards),
    ]
