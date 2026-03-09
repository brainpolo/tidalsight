"""
Django settings for production.
"""

import logging
import os

from axiom_py import Client
from axiom_py.logging import AxiomHandler

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
                "max_size": 6,
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

# Axiom — centralized log ingestion
AXIOM_TOKEN: str = os.environ["AXIOM_TOKEN"]
AXIOM_ORG_ID: str = os.environ["AXIOM_ORG_ID"]
AXIOM_DATASET: str = os.environ.get("AXIOM_DATASET", "tidalsight")

_axiom_handler = AxiomHandler(
    client=Client(token=AXIOM_TOKEN, org_id=AXIOM_ORG_ID),
    dataset=AXIOM_DATASET,
    level=logging.INFO,
)

# Override base LOGGING: replace rich console with plain StreamHandler + Axiom
LOGGING["formatters"]["plain"] = {  # noqa: F405
    "format": "[{levelname}] {name}: {message}",
    "style": "{",
}
LOGGING["handlers"] = {  # noqa: F405
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "plain",
        "level": "INFO",
    },
    "axiom": {
        "()": lambda: _axiom_handler,
    },
}

# All app loggers send to both console (Railway logs) and Axiom
for _logger_name in ("analyst", "scraper", "core", "django.request"):
    LOGGING["loggers"][_logger_name]["handlers"] = ["console", "axiom"]  # noqa: F405

STORAGES: dict[str, dict[str, str]] = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
