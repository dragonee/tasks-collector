#!/bin/sh

set -e

REQUIREMENTS=/app/requirements/local.txt

pip3 install -r $REQUIREMENTS
celery -A tasks worker -l INFO