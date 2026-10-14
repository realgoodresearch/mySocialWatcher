import multiprocessing
import logging

bind = "0.0.0.0:8000"

# Send access and error logs to stdout
# accesslog = "-"
errorlog = "-"

# Log level (info is usually good for production)
loglevel = "info"

# Capture print statements and logs from subprocesses (e.g., Flask app logs)
capture_output = False

# One worker per core (or slightly more if low CPU load)
workers = round(multiprocessing.cpu_count() / 2)

# Type of worker ('sync', 'gthread')
worker_class = "gthread"  # default = 'sync'

# [if 'sync' workers] Limit concurrent connections per worker (helps avoid overload)
# worker_connections = 1000

# [if 'gthread' workers] Number of threads per worker - allows concurrency without needing more processes
threads = 3

# Allow long-running requests (e.g., large POSTs)
timeout = 120  # Keep this unless you notice timeouts under load

# Keep recycling disabled while validating the upgrade and memory usage.
# Re-enable only after testing worker replacement under concurrent load.
# Recycling limits the impact of memory growth; it does not fix memory leaks.
# With Gunicorn 20.1.0, recycling every 500-600 requests coincided with upstream
# connection resets/502s. Gunicorn 26.2.0 has been stable with recycling disabled
# and roughly 1.1 GiB container memory during four-crawler ingestion. Recycling
# on the upgraded version has NOT yet been validated under load.
#
# If memory grows continually across full crawl cycles and representative large
# read queries, an initial experiment could use:
#   max_requests = 10000
#   max_requests_jitter = 2000
# These are per-worker request counts, not seconds or memory limits; each worker
# would recycle after 10000-12000 requests. Jitter staggers restarts but does not
# guarantee that they cannot overlap or that requests cannot be dropped.
# Choose the final threshold from measured memory growth and request throughput,
# leaving room for large queries and worker replacement. Test enough traffic to
# observe multiple recycle cycles while monitoring worker/container memory,
# request latency, nginx 5xx responses, and crawler failures. Raising the count
# alone reduces restart frequency; it does not resolve a recycling-related bug.
# Keep recycling disabled if memory stays bounded and no safeguard is needed.
max_requests = 0
max_requests_jitter = 0


# Enable keep-alive to reduce connection churn
keepalive = 5  # seconds


def when_ready(server):
    server.log.info(
        f"🚀 Gunicorn starting with {server.cfg.workers} workers, {server.cfg.threads} threads per worker"
    )
