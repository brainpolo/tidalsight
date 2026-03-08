"""
Django settings for production.
"""

import os

from tidalsight.settings.base import *  # noqa: F403

ALLOWED_HOSTS: list[str] = ["tidalsight.com"]
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

STORAGES: dict[str, dict[str, str]] = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
