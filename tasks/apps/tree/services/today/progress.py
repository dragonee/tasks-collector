"""Progress-counted task markers.

A task line may carry a counter in parentheses anywhere in its text:

- ``Do tasks (3)`` — three steps, none done yet.
- ``Buy (5) apples`` — five steps in mid-text position.
- ``(2/4) Walk 1km`` — already at two of four.

The first such marker in the line is what we track; any other digits in
parens further along are ignored. Markers with ``total == 0`` (e.g. ``(0)``
or ``(3/0)``) are not progressable and are reported as "not a progress
task" so the caller can fall through to plain boolean done/not-done.
"""

import re
from dataclasses import dataclass
from typing import Optional

# First occurrence wins. The second group is optional: ``(N)`` for fresh
# tasks, ``(K/N)`` for in-progress tasks.
PROGRESS_RE = re.compile(r"\((\d+)(?:/(\d+))?\)")


@dataclass(frozen=True)
class Progress:
    current: int
    total: int
    span: tuple  # (start, end) of the marker within the source text


def parse_progress(text):
    """Return a Progress for the first marker in ``text``, or None if no
    valid marker is present.

    ``current`` is **not** clamped — over-quota markers like ``(4/3)`` are
    legitimate states reachable via the "Add another" action on a
    fully-completed task. ``total < 1`` is still rejected (a zero-step
    task has no meaningful progression).
    """
    if not text:
        return None
    match = PROGRESS_RE.search(text)
    if match is None:
        return None
    first, second = match.group(1), match.group(2)
    if second is None:
        # ``(N)`` form — fresh task with N steps.
        total = int(first)
        current = 0
    else:
        current = int(first)
        total = int(second)
    if total < 1:
        return None
    return Progress(current=current, total=total, span=match.span())


def render_progress(text, progress, new_current):
    """Replace the marker in ``text`` (at ``progress.span``) with the
    rendered form for ``new_current/progress.total``.

    - ``new_current <= 0`` → ``(total)`` (pristine)
    - ``new_current > 0`` → ``(new_current/total)``; ``new_current`` may
      exceed ``total`` (over-quota completion via "Add another").
    """
    start, end = progress.span
    if new_current <= 0:
        marker = f"({progress.total})"
    else:
        marker = f"({new_current}/{progress.total})"
    return text[:start] + marker + text[end:]
