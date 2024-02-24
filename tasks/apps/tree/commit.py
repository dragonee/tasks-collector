from functools import reduce
from collections import OrderedDict
from copy import deepcopy



def transition_markers_in_tree_item(markers):
    new_markers = {
        "weeksInList": 0 if markers.get('madeProgress', False) else markers['weeksInList'] + 1,
        "important": markers['important'],
        "finalizing": markers['finalizing'],
        "canBeDoneOutsideOfWork": markers['canBeDoneOutsideOfWork'],
        "canBePostponed": markers['canBePostponed'],
        "postponedFor": max(0, markers['postponedFor'] - 1),
        "madeProgress": False,
    }

    value = markers.get('transition')

    if value:
        new_markers['transition'] = value

    return new_markers


def transition_data_in_tree_item(item):
    return {
        "text": item['text'],
        "children": transition_data_between_boards(item['children']),

        "data": {
            "text": item['data']['text'],
            "state": item['data']['state'],
            "meaningfulMarkers": transition_markers_in_tree_item(item['data']['meaningfulMarkers']),
        },

        'state': {
            'visible': True if item['data']['meaningfulMarkers']['postponedFor'] == 1 else item['state']['visible']
        }
    }


def filter_out_checked_items(x):
    """Return True if should be filtered out"""

    if x.get('data', {}).get('meaningfulMarkers', {}).get('canBePostponed', False):
        return False

    return x.get('state', {}).get('checked', False)


def transition_data_between_boards(state):
    items = filter(lambda x: not filter_out_checked_items(x), state)

    return list(map(transition_data_in_tree_item, items))


def recursively(collection, f, c, key='children'):
    return c([c((recursively(item[key], f, c), f(item))) for item in collection])


def unionize_sets(items):
    return reduce(lambda x, y: x.union(y if isinstance(y, set) else set([y])), items, set())


def cut_leaves(board_state, thread_name, implied=False):
    new_board_state = []

    for item in board_state:
        # None or string
        item_thread_name = item['data']['meaningfulMarkers'].get('transition')

        new_implied = item_thread_name or implied

        children = cut_leaves(item['children'], thread_name, implied=new_implied)

        if children or (item_thread_name == thread_name and implied == False) or implied == thread_name:
            try:
                del item['data']['meaningfulMarkers']['transition']
            except KeyError:
                pass

            new_board_state.append(item)

        item['children'] = children

    return new_board_state


def merge(a, b):
    names_a = OrderedDict((item['data']['text'], index) for index,item in enumerate(a))
    names_b = OrderedDict((item['data']['text'], index) for index,item in enumerate(b))

    common = set(names_a.keys()).intersection(names_b.keys())

    in_b = set(names_b.keys()).difference(names_a.keys())

    for key in common:
        item_a = a[names_a[key]]
        item_b = b[names_b[key]]

        item_a['children'] = merge(item_a['children'], item_b['children'])

    return a + [b[names_b[key]] for key in in_b]


def pprint(board_state, level=0):
    for item in board_state:
        print("  " * level, item['data']['text'], flush=True)
        pprint(item['children'], level + 1)


def calculate_changes_per_board(state):
    new_state = transition_data_between_boards(state)

    # recursively find all boards referenced by "transition fields"
    thread_names = recursively(
        new_state,
        lambda item: item['data']['meaningfulMarkers'].get('transition'),
        unionize_sets
    )

    return {name: cut_leaves(deepcopy(new_state), name) for name in thread_names}