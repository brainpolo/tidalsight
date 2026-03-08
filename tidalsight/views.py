from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def health(request):
    checks = {}

    # Database
    try:
        connection.ensure_connection()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = str(e)

    # Redis
    try:
        cache.set("_health", 1, 5)
        cache.get("_health")
        checks["cache"] = "ok"
    except Exception as e:
        checks["cache"] = str(e)

    healthy = all(v == "ok" for v in checks.values())
    return JsonResponse(checks, status=200 if healthy else 503)
