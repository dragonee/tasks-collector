#!/bin/sh

set -e

REQUIREMENTS=/app/requirements/local.txt

pip3 install -r $REQUIREMENTS
/app/manage.py runcelery beat -l info