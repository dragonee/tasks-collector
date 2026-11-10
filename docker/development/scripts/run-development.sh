#!/bin/sh

set -e

MANAGE_PY=/app/manage.py
REQUIREMENTS=/app/requirements/local.txt

pip3 install -r $REQUIREMENTS
$MANAGE_PY migrate

# Create superuser for development before loading fixtures, so per-user
# data can be provisioned for it. That command fails if the user exists.
set +e

DJANGO_SUPERUSER_PASSWORD=django $MANAGE_PY createsuperuser --noinput --username django --email django@example.org

set -e

$MANAGE_PY loaddata tasks/fixtures/dev/initial_state.json

$MANAGE_PY runserver 0.0.0.0:8000