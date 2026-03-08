"""
ASGI config for tidalsight project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from dotenv import load_dotenv

load_dotenv()

env_type = os.environ.get("ENV_TYPE", "local")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"tidalsight.settings.{env_type}")

application = get_asgi_application()
