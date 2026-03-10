"""
Django settings for production.
"""

import os

from tidalsight.settings.base import *  # noqa: F403

ALLOWED_HOSTS: list[str] = ["tidalsight.com", "healthcheck.railway.app"]
CSRF_TRUSTED_ORIGINS: list[str] = ["https://tidalsight.com"]

# Database — Railway provides these env vars when you add a PostgreSQL service
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["PGDATABASE"],
        "USER": os.environ["PGUSER"],
        "PASSWORD": os.environ["PGPASSWORD"],
        "HOST": os.environ["PGHOST"],
        "PORT": os.environ["PGPORT"],
        "OPTIONS": {
            "pool": {
                "min_size": 2,
                "max_size": 4,
            },
        },
    }
}

# Cache — Railway provides REDIS_URL when you add a Redis service
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ["REDIS_URL"],
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Celery — uses the same Redis
CELERY_BROKER_URL = os.environ["REDIS_URL"]
CELERY_RESULT_BACKEND = "django-db"

# Override base LOGGING: replace rich console with plain StreamHandler for Railway
LOGGING["formatters"]["plain"] = {  # noqa: F405
    "format": "[{levelname}] {name}: {message}",
    "style": "{",
}
LOGGING["handlers"]["console"] = {  # noqa: F405
    "class": "logging.StreamHandler",
    "formatter": "plain",
    "level": "INFO",
}

STORAGES: dict[str, dict[str, str]] = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
