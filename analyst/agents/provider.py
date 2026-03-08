import threading

from agents.models.openai_provider import OpenAIProvider
from django.conf import settings

_provider = None
_lock = threading.Lock()


def get_model_provider() -> OpenAIProvider:
    global _provider
    if _provider is not None:
        return _provider
    with _lock:
        if _provider is None:
            _provider = OpenAIProvider(
                api_key=settings.BYTEPLUS_MODELARK_KEY,
                base_url=settings.BYTEPLUS_MODELARK_BASE_URL,
                use_responses=False,
            )
    return _provider
