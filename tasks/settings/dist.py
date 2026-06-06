from .base import *

try:
    from .email import *
except ImportError:
    EMAIL_USE_TLS = False
    EMAIL_HOST = "127.0.0.1"
    EMAIL_PORT = 25
    EMAIL_HOST_USER = "[host]"
    EMAIL_HOST_PASSWORD = "[password]"

    DEFAULT_FROM_EMAIL = "[default]"
    SERVER_EMAIL = "[server]"


DEBUG = False

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

ALLOWED_HOSTS = ["tasks.polybrain.org", "localhost"]

# Admins
ADMINS = (("Michał Moroz", "michal@makimo.pl"),)

MANAGERS = ADMINS

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
        },
        "simple": {"format": "%(levelname)s %(message)s"},
    },
    "handlers": {
        "mail_admins": {
            "class": "django.utils.log.AdminEmailHandler",
            "level": "ERROR",
            "include_html": True,
        },
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "debug_file_handler": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "verbose",
            "filename": os.path.join(BASE_DIR, "logs", "debug.log"),
            "maxBytes": 10485760,
            "backupCount": 20,
            "encoding": "utf8",
        },
        "info_file_handler": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "verbose",
            "filename": os.path.join(BASE_DIR, "logs", "info.log"),
            "maxBytes": 10485760,
            "backupCount": 20,
            "encoding": "utf8",
        },
    },
    "loggers": {
        "apps": {
            "level": "DEBUG",
            "handlers": ["debug_file_handler", "info_file_handler"],
        },
        "django": {
            "handlers": ["debug_file_handler", "info_file_handler"],
            "level": "INFO",
            "propagate": True,
        },
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
    },
}


STATIC_ROOT = os.path.join(BASE_DIR, "static", "dist")

FIXTURE_DIRS = [
    os.path.join(BASE_DIR, "fixtures", "dist"),
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": "/var/tmp/django_cache",
    }
}

# Production uses real AWS S3: no custom endpoint, virtual-hosted addressing.
# Credentials and bucket come from the environment (no MinIO defaults here).
# Skipped when an aws.py settings module already supplied the configuration.
if not AWS_CONFIG_FROM_FILE:
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL", "") or None
    AWS_S3_PUBLIC_ENDPOINT_URL = (
        os.environ.get("AWS_S3_PUBLIC_ENDPOINT_URL", "") or None
    )
    # Browser-facing endpoint for the web trip views; defaults to the public
    # (device) endpoint, which in prod is the real bucket host anyway.
    AWS_S3_WEB_ENDPOINT_URL = (
        os.environ.get("AWS_S3_WEB_ENDPOINT_URL", "") or AWS_S3_PUBLIC_ENDPOINT_URL
    )
    AWS_S3_ADDRESSING_STYLE = os.environ.get("AWS_S3_ADDRESSING_STYLE", "virtual")
