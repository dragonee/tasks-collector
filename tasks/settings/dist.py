import environ

from .base import *

# Production is configured from the environment (the container's --env-file,
# see docker/production/.env.example), not from db.py/email.py modules.
env = environ.Env()

DEBUG = False

SECRET_KEY = env("SECRET_KEY")

DATABASES = {"default": env.db()}

# e.g. smtp+tls://user:password@smtp.example.com:587 (URL-encode the password)
globals().update(env.email_url("EMAIL_URL", default="smtp://127.0.0.1:25"))

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="webmaster@localhost")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["tasks.polybrain.org", "localhost"])

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")

# WhiteNoise serves the static files baked into the image
MIDDLEWARE = (
    MIDDLEWARE[:1] + ["whitenoise.middleware.WhiteNoiseMiddleware"] + MIDDLEWARE[1:]
)

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
    },
    # Log to stdout for `docker logs`; the deploy caps the log size per container
    "loggers": {
        "apps": {
            "level": "DEBUG",
            "handlers": ["console"],
        },
        "django": {
            "handlers": ["console"],
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
