from datetime import datetime
from pathlib import Path
from django.conf import settings

# Cache for APP_VERSION
_app_version_cache = {'loaded': False, 'version': None}

def menu(request):
    return {
        'current_year': datetime.now().year
    }

def app_version(request):
    """Context processor to provide APP_VERSION from REVISION file.

    Reads the REVISION file (created during deployment) and caches it in memory.
    Returns None if the file doesn't exist (e.g., in development).
    """
    global _app_version_cache

    # Return cached value if already loaded
    if _app_version_cache['loaded']:
        return {'APP_VERSION': _app_version_cache['version']}

    # Try to read REVISION file
    revision_file = Path(settings.BASE_DIR) / 'REVISION'

    if revision_file.exists():
        try:
            _app_version_cache['version'] = revision_file.read_text().strip()
        except (OSError, IOError):
            pass

    _app_version_cache['loaded'] = True
    return {'APP_VERSION': _app_version_cache['version']}