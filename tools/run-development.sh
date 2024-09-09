#!/bin/sh

set -e

MANAGE_PY=/app/manage.py
REQUIREMENTS=/app/requirements/local.txt

pip3 install -r $REQUIREMENTS
$MANAGE_PY migrate
$MANAGE_PY loaddata tasks/fixtures/dev/initial_state.json

# Create superuser for development. That command might fail
set +e

DJANGO_SUPERUSER_PASSWORD=django $MANAGE_PY createsuperuser --noinput --username django --email django@example.org

set -e

$MANAGE_PY runserver 0.0.0.0:8000