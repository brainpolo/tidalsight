"""
Django base settings for tidalsight project.

Settings common to all environments.
"""

import logging
import os
from pathlib import Path
from typing import Any

from axiom_py import Client
from axiom_py.logging import AxiomHandler
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

# When off, asset creation won't trigger peer discovery (prevents recursive crawling)
CRAWLER_ON: bool = os.environ.get("CRAWLER_ON", "true").lower() == "true"


# Application definition -----------------------------------------------

INSTALLED_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
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
    "core.middleware.eager_user_middleware",
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
                "core.context_processors.vite",
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


# Axiom — centralized log ingestion (graceful: app works without it)
_axiom_handler = None
_AXIOM_TOKEN = os.environ.get("AXIOM_TOKEN")
_AXIOM_ORG_ID = os.environ.get("AXIOM_ORG_ID")
AXIOM_DATASET: str = os.environ.get("AXIOM_DATASET", "tidalsight")

if _AXIOM_TOKEN and _AXIOM_ORG_ID:
    try:
        _axiom_handler = AxiomHandler(
            client=Client(
                token=_AXIOM_TOKEN,
                org_id=_AXIOM_ORG_ID,
                edge_url="https://eu-central-1.aws.edge.axiom.co",
            ),
            dataset=AXIOM_DATASET,
            level=logging.INFO,
        )
        logging.getLogger(__name__).info("Axiom logging successfully configured.")
    except Exception:
        logging.getLogger(__name__).warning(
            "Failed to initialise Axiom handler, continuing without it"
        )

# Logging
_LOG_HANDLERS: list[str] = ["console", "axiom"] if _axiom_handler else ["console"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "rich": {
            "format": "%(message)s",
            "datefmt": "[%X]",
        },
    },
    "handlers": {
        "console": {
            "class": "rich.logging.RichHandler",
            "formatter": "rich",
            "level": "DEBUG",
            "rich_tracebacks": True,
            "tracebacks_suppress": ["django"],
            "show_path": True,
        },
        **({"axiom": {"()": lambda: _axiom_handler}} if _axiom_handler else {}),
    },
    "loggers": {
        "analyst": {
            "handlers": _LOG_HANDLERS,
            "level": "INFO",
            "propagate": False,
        },
        "scraper": {
            "handlers": _LOG_HANDLERS,
            "level": "INFO",
            "propagate": False,
        },
        "core": {
            "handlers": _LOG_HANDLERS,
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": _LOG_HANDLERS,
            "level": "WARNING",
            "propagate": False,
        },
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
