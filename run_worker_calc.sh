#!/bin/bash

echo 'starting Subsea Worker'

/usr/bin/tmux new-session -d 'celery -A subsea.server worker --loglevel=INFO --concurrency=1 -n subsea_worker1 -Q calculation'

