from functools import cache

from byteplussdkarkruntime import Ark
from django.conf import settings

from analyst.llms import SKYLARK_EMBEDDING


@cache
def _get_client() -> Ark:
    return Ark(
        api_key=settings.BYTEPLUS_MODELARK_KEY,
        base_url=settings.BYTEPLUS_MODELARK_BASE_URL,
    )


def gen_text_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text using Skylark multimodal embeddings."""
    client = _get_client()
    resp = client.multimodal_embeddings.create(
        model=SKYLARK_EMBEDDING,
        input=[{"type": "text", "text": text}],
    )
    return resp.data["embedding"]
