import sys
import contextlib
import re
import os
import json
from datetime import datetime

SHORT_TIMEOUT = 3.05

DEAD_LETTER_DIRECTORY = os.path.expanduser(os.path.join('~', '.tasks', 'queue'))


def ensure_directory_exists(file_path):
    """Ensure the directory for the given file path exists."""
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def queue_dead_letter(payload, path, metadata, file_type="item"):
    """Queue a payload to be sent later when connection is restored."""
    ensure_directory_exists(path)

    basename = datetime.now().strftime(f"%Y-%m-%d_%H%M%S_{file_type}")
    name = f'{basename}.json'
    i = 0

    while os.path.exists(os.path.join(path, name)):
        i += 1
        name = f'{basename}-{i}.json'

    with open(os.path.join(path, name), "w") as f:
        json.dump({
            'payload': payload,
            'meta': metadata
        }, f)

    return name


def send_dead_letter(path, _metadata):
    """Send a single queued dead letter."""
    import requests

    metadata = _metadata.copy()

    print(f"Attempting to send {path}...")

    with open(path) as f:
        data = json.load(f)

    metadata.update(data['meta'])
    payload = data['payload']

    requests.post(metadata['url'], json=payload, auth=metadata['auth'])

    os.unlink(path)


def send_dead_letters(path, metadata):
    """Send all queued dead letters in a directory."""
    ensure_directory_exists(path)
    for root, dirs, files in os.walk(path):
        for name in sorted(files):
            send_dead_letter(os.path.join(root, name), metadata)


def queue_failed_request(payload, metadata, file_type):
    """Queue a failed request to be retried later."""
    return queue_dead_letter(payload, DEAD_LETTER_DIRECTORY, metadata, file_type)


def retry_failed_requests(metadata):
    """Retry all failed requests that were queued."""
    send_dead_letters(DEAD_LETTER_DIRECTORY, metadata)

@contextlib.contextmanager
def smart_open(filename=None, mode='r', pipe=None, **kwargs):
    if filename and filename != '-':
        fh = open(filename, mode=mode, **kwargs)
    elif pipe is not None:
        fh = pipe
    else:
        fh = sys.stdin if mode.startswith('r') else sys.stdout

    try:
        yield fh
    finally:
        if fh not in (sys.stdout, sys.stderr, sys.stdin):
            fh.close()


def sanitize_string(value):
    return value.strip().replace('\n', '\r\n') if value else None

def sanitize_list_of_strings(value):
    return list(filter(None, map(str.strip, value)))

def sanitize_fields(payload, mapping=None):
    mapping = mapping or {}

    return {k: mapping.get(k, sanitize_string)(v) for k, v in payload.items()}


def itemize_string(value, prepend=None, append=None, prefix="- "):
    if value is None:
        return ''

    s = "\n".join([prefix + line.strip() if line.strip() else line for line in value.split("\n")])

    if prepend:
        s = prepend + s

    if append:
        s = s + append

    return s

def get_cursor_position(template, search_string):
    comment_index = template.find(search_string)
    if comment_index != -1:
        newlines_before_comment = template[:comment_index].count('\n')
    else:
        newlines_before_comment = 0

    return newlines_before_comment + 3


def _get_value(obj, key):
    if isinstance(obj, dict):
        return obj[key]
    if isinstance(obj, list):
        return obj[int(key)]
    if callable(obj):
        return obj(key)
    attr = getattr(obj, key)
    if callable(attr):
        return attr()
    return attr


def getter(obj, key: tuple[str, ...], default=None):
    item = _get_value(obj, key[0])

    if item is None:
        return default

    if len(key) == 1:
        return item
    
    return getter(item, key[1:])


def render_template(template, context):
    def replace_var(match):
        var_name = match.group(1)
        return str(getter(context, var_name.split('.'), default=''))

    def eval_if(match):
        def parse_condition(condition_str):
            # Handle both AND and OR conditions with AND having precedence
            # Split by OR first (lower precedence)
            or_parts = re.split(r'\s+or\s+', condition_str)
            
            if len(or_parts) > 1:
                # OR condition: any part can be true
                return any(parse_and_condition(part.strip()) for part in or_parts)
            else:
                # No OR, just handle AND
                return parse_and_condition(condition_str)
        
        def parse_and_condition(condition_str):
            # Split by AND (higher precedence)
            and_parts = re.split(r'\s+and\s+', condition_str)
            
            if len(and_parts) > 1:
                # AND condition: all parts must be true
                return all(getter(context, part.strip().split('.')) for part in and_parts)
            else:
                # Simple dot notation
                return getter(context, condition_str.strip().split('.'))
        
        condition = match.group(1)
        true_part = match.group(2)
        try:
            false_part = match.group(3)
        except IndexError:
            false_part = ''
        return true_part if parse_condition(condition) else false_part

    template = re.sub(r'\{% if (.*?) %\}(.*?)\{% else %\}(.*?)\{% endif %\}', eval_if, template, flags=re.DOTALL)
    template = re.sub(r'\{% if (.*?) %\}(.*?)\{% endif %\}', eval_if, template, flags=re.DOTALL)
    template = re.sub(r'\{\{ (.*?) \}\}', replace_var, template)
    template = re.sub(r'\n\s*\n\s*\n', '\n\n', template)

    return template
