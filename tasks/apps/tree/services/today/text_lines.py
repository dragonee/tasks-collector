"""Helpers for the newline-joined text fields backing Plan.focus and
Reflection.good. Exact-line equality, no trimming or case folding."""


def split_lines(value):
    if not value:
        return []
    return value.split("\n")


def has_line(value, line):
    return line in split_lines(value)


def add_unique_line(value, line):
    if not value:
        return line
    if line in value.split("\n"):
        return value
    return value + "\n" + line


def remove_line(value, line):
    if not value:
        return ""
    return "\n".join(l for l in value.split("\n") if l != line)
