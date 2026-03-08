"""
Django base settings for tidalsight project.

Settings common to all environments.
"""

import os
from pathlib import Path
from typing import Any

from django.utils.csp import CSP
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

# Load .env from project root
load_dotenv(BASE_DIR / ".env")

ENV_TYPE: str | None = os.environ.get("ENV_TYPE")
if ENV_TYPE not in ("local", "prod"):
    raise RuntimeError(f"ENV_TYPE must be 'local' or 'prod', got: {ENV_TYPE!r}")

DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"


# Required Environment Variables ---------------------------------------

SECRET_KEY: str = os.environ["SECRET_KEY"]
# BytePlus ModelArk
BYTEPLUS_MODELARK_KEY: str = os.environ["BYTEPLUS_MODELARK_KEY"]
BYTEPLUS_MODELARK_BASE_URL: str = "https://ark.ap-southeast.bytepluses.com/api/v3"
# Brave Search
BRAVE_SEARCH_API_KEY: str = os.environ["BRAVE_SEARCH_API_KEY"]


# Application definition -----------------------------------------------

INSTALLED_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_celery_results",
    "core",
    "scraper",
    "analyst",
]

MIDDLEWARE: list[str] = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "tidalsight.urls"

TEMPLATES: list[dict[str, Any]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
            ],
        },
    },
]

WSGI_APPLICATION = "tidalsight.wsgi.application"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL: str = "static/"
STATIC_ROOT: Path = BASE_DIR / "staticfiles"
STATICFILES_DIRS: list[Path] = [BASE_DIR / "static"]


# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "analyst": {"handlers": ["console"], "level": "INFO"},
        "scraper": {"handlers": ["console"], "level": "INFO"},
    },
}

# Concurrency
SYNC_MAX_WORKERS: int = 2

# Content Security Policy --------------------------------------------------

SECURE_CSP: dict = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.UNSAFE_INLINE, CSP.UNSAFE_EVAL],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE, "https://fonts.googleapis.com"],
    "font-src": [CSP.SELF, "https://fonts.gstatic.com"],
    "img-src": [CSP.SELF, "data:", "https://*.google.com", "https://*.gstatic.com"],
    "connect-src": [CSP.SELF],
    "frame-src": [CSP.NONE],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
}

AUTH_USER_MODEL = "core.User"
LOGIN_URL = "core:sign_in"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"
