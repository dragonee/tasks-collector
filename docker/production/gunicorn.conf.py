import os

# The container runs with --network host, so bind to loopback: only nginx on
# the host should reach gunicorn, not the outside world.
bind = "127.0.0.1:9422"

workers = int(os.environ.get("GUNICORN_WORKERS", 5))

errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

proc_name = "tasks"
