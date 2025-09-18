import os

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'tasks'),
        'USER': os.environ.get('DB_USER', 'tasks'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'secret'),
        'HOST': os.environ.get('DB_HOST', 'tasks-db'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'TEST': {
            'CHARSET': 'UTF8',
            'NAME': os.environ.get('DB_TEST_NAME', 'tasks-test')
        }
    }
}


from .base import *

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEBUG = True

INSTALLED_APPS += ('debug_toolbar',)

DEBUG_TOOLBAR_PATCH_SETTINGS = False

VALIDATE_FRONT_PASSWORD = False

MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware', ] + MIDDLEWARE

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static', 'local')
]

FIXTURE_DIRS = [
    os.path.join(BASE_DIR, 'fixtures', 'tests'),
    os.path.join(BASE_DIR, 'fixtures', 'dev'),
    os.path.join(BASE_DIR, 'fixtures', 'dist'),
]

INTERNAL_IPS = [
    '0.0.0.0',
    '127.0.0.1'
]

WEBPACK_MANIFEST_FILE = os.path.join(BASE_DIR, '../webpack-stats.local.json')

CELERY_BROKER_URL = 'redis://tasks-queue'