from django.conf import settings
from django.http import HttpRequest


def vite(request: HttpRequest) -> dict[str, bool]:
    return {"VITE_DEV": settings.DEBUG}
