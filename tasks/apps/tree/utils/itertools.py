from collections.abc import Hashable, Mapping, Sequence

def itemize(order: Sequence[Hashable], mapping: Mapping[Hashable, object], default=None, item_type=tuple):
    for key in order:
        yield item_type(key, mapping.get(key, default))

def _in_second(func):
    """Apply a function to the second element of a tuple"""
    def wrapped(value):
        first, second = value
        return first, func(second)
    return wrapped

def compose(*functions):
    """Compose a list of functions into a single function"""
    def inner(arg):
        for f in functions:
            arg = f(arg)
        return arg
    return inner