from collections.abc import Hashable, Mapping, Sequence

def itemize(order: Sequence[Hashable], mapping: Mapping[Hashable, object], default=None, item_type=tuple):
    for key in order:
        yield item_type(key, mapping.get(key, default))
