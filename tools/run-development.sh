#!/bin/sh

set -e

MANAGE_PY=/app/manage.py
REQUIREMENTS=/app/requirements/local.txt
WAIT_FOR=/app/tools/wait-for
DATABASE_HOST=tasks-db:5432

pip3 install -r $REQUIREMENTS
npm install
$WAIT_FOR $DATABASE_HOST -- echo 'Database ready'
$MANAGE_PY migrate
$MANAGE_PY loaddata tasks/fixtures/dev/initial_state.json
npm run dev
