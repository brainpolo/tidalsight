"""
WSGI config for tidalsight project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from dotenv import load_dotenv

from django.core.wsgi import get_wsgi_application

load_dotenv()

env_type = os.environ.get("ENV_TYPE", "local")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"tidalsight.settings.{env_type}")

application = get_wsgi_application()
