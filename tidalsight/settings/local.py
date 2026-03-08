"""
Django settings for local development.
"""

from tidalsight.settings.base import *  # noqa: F403

# daphne overrides runserver to use ASGI (must be before django.contrib.staticfiles)
INSTALLED_APPS = ["daphne", *INSTALLED_APPS]  # noqa: F405
ASGI_APPLICATION = "tidalsight.asgi.application"

ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "tidalsight",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Celery
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "django-db"

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://localhost:6379/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}
