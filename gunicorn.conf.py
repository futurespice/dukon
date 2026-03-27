"""
Gunicorn configuration for Dukon Online production.

Worker count is controlled by GUNICORN_WORKERS env var (default 4).
Recommended: 2 × vCPU + 1.

max_requests / max_requests_jitter prevent memory leaks by recycling workers
periodically — each worker handles up to 1000 requests then gracefully restarts.
The jitter (±50) staggers restarts so all workers don't recycle simultaneously.
"""
import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("GUNICORN_WORKERS", 4))
# DEVOPS #3: gthread allows concurrent IO-bound requests per worker.
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", 4))
timeout = 60
keepalive = 5

# Recycle workers to prevent memory leaks.
max_requests = 1000
max_requests_jitter = 50

# On SIGTERM gunicorn sends workers a graceful shutdown signal.
# graceful_timeout gives them time to finish in-flight requests before
# SIGKILL is sent. Critical for zero-downtime rolling deploys.
graceful_timeout = 30

# AUDIT-3 DEVOPS FIX #12: Use tmpfs for worker heartbeat files.
# In Docker, /tmp can be slow (overlay2). /dev/shm is always tmpfs.
worker_tmp_dir = '/dev/shm'

# Logging — stdout/stderr so Docker captures it.
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Forwarded headers from nginx.
forwarded_allow_ips = "*"
proxy_protocol = False
