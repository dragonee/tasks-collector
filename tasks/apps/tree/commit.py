from collections import OrderedDict
from copy import deepcopy
from functools import reduce


def weeks_in_list(markers, children=None):
    """
    Calculate the number of weeks a task has been in the list.

    Args:
        markers (dict): Task meaningful markers containing progress and timing info
        children (list, optional): List of child items (if present, indicates this is a category)

    Returns:
        int: Number of weeks in list, with special handling:
             - 0 if has children (categories don't progress weeksInList)
             - 0 if madeProgress is True (progress resets counter)
             - Current value if postponedFor > 0 (postponed tasks don't increment)
             - Current value + 1 otherwise (normal weekly increment)
    """
    if children:
        return 0

    if markers.get("madeProgress", False):
        return 0

    if markers.get("postponedFor", 0) > 0:
        return markers.get("weeksInList", 0)

    return markers.get("weeksInList", 0) + 1


def transition_markers_in_tree_item(markers, children=None):
    """
    Update meaningful markers for a task during board transition/commit.

    Args:
        markers (dict): Current meaningful markers for the task
        children (list, optional): List of child items to check if this is a category

    Returns:
        dict: Updated markers with:
              - weeksInList updated based on progress/postponement and children
              - postponedFor decremented by 1 (minimum 0)
              - madeProgress reset to False
              - other markers preserved
              - transition field preserved if present
    """
    new_markers = {
        "weeksInList": weeks_in_list(markers, children),
        "important": markers["important"],
        "finalizing": markers["finalizing"],
        "canBeDoneOutsideOfWork": markers["canBeDoneOutsideOfWork"],
        "canBePostponed": markers["canBePostponed"],
        "postponedFor": max(0, markers["postponedFor"] - 1),
        "madeProgress": False,
    }

    value = markers.get("transition")

    if value:
        new_markers["transition"] = value

    return new_markers


def transition_data_in_tree_item(item):
    """
    Transform a single tree item during board transition.

    Args:
        item (dict): Tree item with text, data, state, and children

    Returns:
        dict: Transformed item with:
              - Updated meaningful markers via transition_markers_in_tree_item()
              - Recursively processed children
              - Visibility logic: hidden if postponedFor == 1, otherwise visible
    """
    return {
        "text": item["text"],
        "children": transition_data_between_boards(item["children"]),
        "data": {
            "text": item["data"]["text"],
            "state": item["data"]["state"],
            "meaningfulMarkers": transition_markers_in_tree_item(
                item["data"]["meaningfulMarkers"], item["children"]
            ),
        },
        "state": {
            "visible": (
                True
                if item["data"]["meaningfulMarkers"]["postponedFor"] == 1
                else item.get("state", {}).get("visible", True)
            )
        },
    }


def filter_out_checked_items(x):
    """
    Determine if a task should be filtered out during board transition.

    Args:
        x (dict): Task item with data, state, and meaningful markers

    Returns:
        bool: True if item should be removed, False to keep it

    Filtering rules:
        - Keep all canBePostponed tasks (special handling)
        - Keep all currently postponed tasks (postponedFor > 0)
        - Remove tasks with weeksInList >= 5 (force removal after 6 weeks)
        - Remove checked/completed tasks
    """

    if x.get("data", {}).get("meaningfulMarkers", {}).get("canBePostponed", False):
        return False

    # Don't remove postponed tasks
    if x.get("data", {}).get("meaningfulMarkers", {}).get("postponedFor", 0) > 0:
        return False

    if x.get("data", {}).get("meaningfulMarkers", {}).get("madeProgress", False):
        return False

    # Filter out tasks that have been in the list for 6 weeks or more (force removal)
    weeks_in_list = x.get("data", {}).get("meaningfulMarkers", {}).get("weeksInList", 0)
    if weeks_in_list >= 5:
        return True

    return x.get("state", {}).get("checked", False)


def transition_data_between_boards(state):
    """
    Process a list of board items during transition, filtering and transforming them.

    Args:
        state (list): List of board items to process

    Returns:
        list: Filtered and transformed items with:
              - Checked/completed items removed
              - Long-running tasks (6+ weeks, zero-indexed) removed
              - Remaining items processed via transition_data_in_tree_item()
    """
    items = filter(lambda x: not filter_out_checked_items(x), state)

    return list(map(transition_data_in_tree_item, items))


def recursively(collection, f, c, key="children"):
    """
    Apply function f recursively to a tree structure and combine results with function c.

    Args:
        collection (list): List of tree items to process
        f (callable): Function to apply to each item
        c (callable): Function to combine/reduce results
        key (str): Key name for children items (default: 'children')

    Returns:
        Any: Combined result of applying f to all items and their children,
             then reducing with function c
    """
    return c([c((recursively(item[key], f, c), f(item))) for item in collection])


def unionize_sets(items):
    """
    Combine multiple items into a single set, handling both sets and individual values.

    Args:
        items (iterable): Collection of items that can be sets or individual values

    Returns:
        set: Union of all items, converting individual values to single-item sets
    """
    return reduce(
        lambda x, y: x.union(y if isinstance(y, set) else set([y])), items, set()
    )


def cut_leaves(board_state, thread_name, implied=False):
    """
    Extract items destined for a specific thread, removing transition markers.

    Args:
        board_state (list): List of board items to process
        thread_name (str): Target thread name to extract items for
        implied (bool): Whether the thread context is inherited from parent

    Returns:
        list: Items that belong to the target thread with:
              - Items explicitly marked for the thread
              - Items whose children belong to the thread
              - Transition markers removed from matching items
              - Children recursively processed
    """
    new_board_state = []

    for item in board_state:
        # None or string
        item_thread_name = item["data"]["meaningfulMarkers"].get("transition")

        new_implied = item_thread_name or implied

        children = cut_leaves(item["children"], thread_name, implied=new_implied)

        if (
            children
            or (item_thread_name == thread_name and not implied)
            or implied == thread_name
        ):
            try:
                del item["data"]["meaningfulMarkers"]["transition"]
            except KeyError:
                pass

            new_board_state.append(item)

        item["children"] = children

    return new_board_state


def merge(a, b):
    """
    Merge two lists of board items, combining items with matching text.

    Args:
        a (list): First list of board items (will be modified)
        b (list): Second list of board items to merge in

    Returns:
        list: Merged list where:
              - Items with same text have their children merged recursively
              - Items unique to b are appended to the result
              - Original order from a is preserved, b items added at end
    """
    names_a = OrderedDict((item["data"]["text"], index) for index, item in enumerate(a))
    names_b = OrderedDict((item["data"]["text"], index) for index, item in enumerate(b))

    common = set(names_a.keys()).intersection(names_b.keys())

    in_b = set(names_b.keys()).difference(names_a.keys())

    for key in common:
        item_a = a[names_a[key]]
        item_b = b[names_b[key]]

        item_a["children"] = merge(item_a["children"], item_b["children"])

    return a + [b[names_b[key]] for key in in_b]


def pprint(board_state, level=0):
    """
    Pretty print a board state with hierarchical indentation.

    Args:
        board_state (list): List of board items to print
        level (int): Current indentation level (default: 0)

    Prints each item's text with indentation based on hierarchy level,
    recursively printing children with increased indentation.
    """
    for item in board_state:
        print("  " * level, item["data"]["text"], flush=True)
        pprint(item["children"], level + 1)


def calculate_changes_per_board(state):
    """
    Calculate board transitions by distributing items to their target threads.

    Args:
        state (list): Current board state with items to transition

    Returns:
        dict: Mapping of thread names to their respective board states where:
              - Keys are thread names referenced in transition markers
              - Values are board states with items destined for each thread
              - Items are deep-copied and have transition markers removed
              - All meaningful markers are updated for the transition
    """
    new_state = transition_data_between_boards(state)

    # recursively find all boards referenced by "transition fields"
    thread_names = recursively(
        new_state,
        lambda item: item["data"]["meaningfulMarkers"].get("transition"),
        unionize_sets,
    )

    return {name: cut_leaves(deepcopy(new_state), name) for name in thread_names}
