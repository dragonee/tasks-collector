"""Helpers for the newline-joined text fields backing Plan.focus and
Reflection.good. Exact-line equality, no trimming or case folding.

CRLF / CR endings are normalized to LF (some writers store ``\\r\\n`` — e.g.
the CLI's ``sanitize_string``), so a line never carries a stray ``\\r`` and
matching stays consistent across fields. Functions that rewrite a field
return it normalized."""


def _normalize(value):
    return value.replace("\r\n", "\n").replace("\r", "\n")


def split_lines(value):
    if not value:
        return []
    return _normalize(value).split("\n")


def has_line(value, line):
    return line in split_lines(value)


def add_unique_line(value, line):
    lines = split_lines(value)
    if line in lines:
        return "\n".join(lines)
    return "\n".join(lines + [line])


def remove_line(value, line):
    return "\n".join(l for l in split_lines(value) if l != line)


def replace_line(value, old_line, new_line):
    """Replace exact-match occurrences of old_line with new_line, preserving
    the position of other lines. Returns the (normalized) value unchanged if
    old_line is not present.
    """
    lines = split_lines(value)
    if old_line not in lines:
        return "\n".join(lines)
    return "\n".join(new_line if l == old_line else l for l in lines)
