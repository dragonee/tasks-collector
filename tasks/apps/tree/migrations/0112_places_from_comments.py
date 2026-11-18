"""A trip note's or photo's place, written so far as its comment's first line
(#poi lat=… lng=…, the tag also #coords, #coordinates or #latlng), becomes
its EventLocation, and the line leaves the comment.

What it changed is kept in tree_journaladded_before_0112, a table of its own:
reversing puts each line back and takes the location away. An entry whose
comment changed since keeps it.
"""

import math
import re

from django.db import migrations

# The line as the phones wrote it (services.locations, as it was).
PLACE_LINE = re.compile(
    r"\A[ \t]*#(?:poi|coords|coordinates|latlng)\b"
    r"[^\n]*?\blat\s*=\s*(-?\d+(?:\.\d+)?)"
    r"[^\n]*?\blng\s*=\s*(-?\d+(?:\.\d+)?)"
    r"(?:[^\n]*?\bacc\s*=\s*(\d+(?:\.\d+)?))?"
    r"[^\n]*(?:\n|\Z)",
    re.IGNORECASE,
)

CHANGED = "tree_journaladded_before_0112"


def place(match):
    lat, lng = float(match.group(1)), float(match.group(2))
    acc = float(match.group(3)) if match.group(3) else None
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng, acc


def move_places(apps, schema_editor):
    JournalAdded = apps.get_model("tree", "JournalAdded")
    EventLocation = apps.get_model("tree", "EventLocation")

    schema_editor.execute(
        f"CREATE TABLE {CHANGED} ("
        "event_id integer PRIMARY KEY,"
        " comment_before text NOT NULL, comment_after text NOT NULL)"
    )

    entries = JournalAdded.objects.filter(
        comment__iregex=r"^[ \t]*#(poi|coords|coordinates|latlng)"
    ).only("comment")
    changed = []
    for entry in entries.iterator():
        match = PLACE_LINE.match(entry.comment)
        found = place(match) if match else None
        if found is None:
            continue
        after = entry.comment[match.end() :]
        EventLocation.objects.create(
            event_id=entry.pk, lat=found[0], lng=found[1], acc=found[2]
        )
        JournalAdded.objects.filter(pk=entry.pk).update(comment=after)
        changed.append((entry.pk, entry.comment, after))

    with schema_editor.connection.cursor() as cursor:
        cursor.executemany(f"INSERT INTO {CHANGED} VALUES (%s, %s, %s)", changed)


def put_back(apps, schema_editor):
    JournalAdded = apps.get_model("tree", "JournalAdded")
    EventLocation = apps.get_model("tree", "EventLocation")

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [CHANGED])
        if cursor.fetchone()[0] is None:
            return
        cursor.execute(f"SELECT event_id, comment_before, comment_after FROM {CHANGED}")
        rows = cursor.fetchall()

    for pk, before, after in rows:
        JournalAdded.objects.filter(pk=pk, comment=after).update(comment=before)
        EventLocation.objects.filter(event_id=pk).delete()

    schema_editor.execute(f"DROP TABLE {CHANGED}")


class Migration(migrations.Migration):

    dependencies = [
        ("tree", "0111_event_location"),
    ]

    operations = [
        migrations.RunPython(move_places, put_back),
    ]
