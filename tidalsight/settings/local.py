"""
Django settings for local development.
"""

from tidalsight.settings.base import *  # noqa: F403

# Vite dev server CSP overrides
_VITE = "http://localhost:5173"
SECURE_CSP = {
    **SECURE_CSP,  # noqa: F405
    "script-src": [*SECURE_CSP["script-src"], _VITE],  # noqa: F405
    "style-src": [*SECURE_CSP["style-src"], _VITE],  # noqa: F405
    "connect-src": [*SECURE_CSP["connect-src"], _VITE, "ws://localhost:5173"],  # noqa: F405
}

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
        "OPTIONS": {
            "pool": {
                "min_size": 2,
                "max_size": 6,
            },
        },
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
