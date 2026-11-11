"""Checks on rendered HTML that a test posting to a view can't make."""

from html.parser import HTMLParser


class _FormNesting(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.nested = []

    def handle_starttag(self, tag, attrs):
        if tag != "form":
            return
        if self.depth:
            self.nested.append(self.get_starttag_text())
        self.depth += 1

    def handle_endtag(self, tag):
        if tag == "form" and self.depth:
            self.depth -= 1


def nested_forms(html):
    """The start tags of forms opened inside another form.

    A browser drops such a tag: the inner form's fields join the outer form,
    and its buttons submit the outer one.
    """
    parser = _FormNesting()
    parser.feed(html)
    parser.close()
    return parser.nested
