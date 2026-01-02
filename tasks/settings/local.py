import os
import sys

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "tasks"),
        "USER": os.environ.get("DB_USER", "tasks"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "secret"),
        "HOST": os.environ.get("DB_HOST", "tasks-db"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "TEST": {
            "CHARSET": "UTF8",
            "NAME": os.environ.get("DB_TEST_NAME", "tasks-test"),
        },
    }
}


from .base import *

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEBUG = True

is_running_tests = "test" in sys.argv or os.environ.get("PYTEST_VERSION") is not None

if not is_running_tests:
    INSTALLED_APPS += ("debug_toolbar",)
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
    DEBUG_TOOLBAR_PATCH_SETTINGS = False
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda _request: DEBUG,
    }


VALIDATE_FRONT_PASSWORD = False

STATICFILES_DIRS = [os.path.join(BASE_DIR, "static", "local")]

FIXTURE_DIRS = [
    os.path.join(BASE_DIR, "fixtures", "tests"),
    os.path.join(BASE_DIR, "fixtures", "dev"),
    os.path.join(BASE_DIR, "fixtures", "dist"),
]

INTERNAL_IPS = ["0.0.0.0", "127.0.0.1"]

CELERY_BROKER_URL = "redis://tasks-queue"
