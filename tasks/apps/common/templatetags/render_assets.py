from pathlib import Path

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

register = template.Library()

# In-memory caches for CSS and JS tag files
CSS_FILES = {}
JS_FILES = {}


def get_potential_staticfile_paths(filename):
    """Yields potential paths for a static file.

    Args:
        filename - Name of the file to search for
    Yields:
        Path objects to check, in order of preference
    """

    # First check STATIC_ROOT (production)
    if hasattr(settings, 'STATIC_ROOT') and settings.STATIC_ROOT:
        yield Path(settings.STATIC_ROOT) / filename

    # Then check all STATICFILES_DIRS (development)
    if hasattr(settings, 'STATICFILES_DIRS') and settings.STATICFILES_DIRS:
        for static_dir in settings.STATICFILES_DIRS:
            yield Path(static_dir) / filename


def read_cached_staticfile(entry_point, file_type, cache):
    """Reads and caches static tag files.

    Args:
        entry_point - Name of the entry point (e.g., 'app', 'hello_world_mount')
        file_type - Type of file ('css' or 'js')
        cache - Dictionary to use for caching
    Returns:
        HTML content from the cached file or empty string if not found.
    """
    # Check if already cached
    if entry_point in cache:
        return cache[entry_point]

    filename = f'{entry_point}-{file_type}-tags.html'

    # Find first existing file
    html_file_path = next(
        (path for path in get_potential_staticfile_paths(filename) if path.exists()),
        None
    )

    if html_file_path is None:
        # No file found, cache empty string
        cache[entry_point] = ''
        return ''

    try:
        content = html_file_path.read_text()
        # Cache the content
        cache[entry_point] = content
        return content
    except (FileNotFoundError, OSError):
        # Cache empty string to avoid repeated file lookups
        cache[entry_point] = ''
        return ''


def read_cached_js(entry_point, cache=JS_FILES):
    """Reads and caches JS tag files."""
    return read_cached_staticfile(entry_point, 'js', cache)


def read_cached_css(entry_point, cache=CSS_FILES):
    """Reads and caches CSS tag files."""
    return read_cached_staticfile(entry_point, 'css', cache)


@register.simple_tag
def render_js(entry_point):
    """Loads HTML file with script tags for a specific entry point.

    Args:
        entry_point - Name of the entry point (e.g., 'app', 'hello_world_mount')
    Returns:
        HTML content from the entry point's js-tags.html file.
    """
    content = read_cached_js(entry_point)
    return mark_safe(content)


@register.simple_tag
def render_css(entry_point):
    """Loads HTML file with CSS link tags for a specific entry point.

    Args:
        entry_point - Name of the entry point (e.g., 'app', 'hello_world_mount')
    Returns:
        HTML content from the entry point's css-tags.html file.
    """
    content = read_cached_css(entry_point)
    return mark_safe(content)

