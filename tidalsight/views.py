import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health(request):
    checks = {}

    # Database
    try:
        connection.ensure_connection()
        checks["db"] = "ok"
    except Exception:
        logger.exception("Health check: database connection failed")
        checks["db"] = "error"

    # Redis
    try:
        cache.set("_health", 1, 5)
        cache.get("_health")
        checks["cache"] = "ok"
    except Exception:
        logger.exception("Health check: cache connection failed")
        checks["cache"] = "error"

    healthy = all(v == "ok" for v in checks.values())
    return JsonResponse(checks, status=200 if healthy else 503)
