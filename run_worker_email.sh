#!/bin/bash

echo 'starting Subsea Emailer'

/usr/bin/tmux new-session -d 'celery -A subsea.server worker --loglevel=INFO --concurrency=1 -n subsea_worker2 -Q notification'

