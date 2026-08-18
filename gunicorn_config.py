import os
from pathlib import Path


port = os.environ.get("PORT", "8080")
bind = f"0.0.0.0:{port}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
worker_tmp_dir = "/dev/shm" if Path("/dev/shm").exists() else "/tmp"
