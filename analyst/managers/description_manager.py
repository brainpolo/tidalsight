import logging

from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.description_agent import description_agent
from analyst.app_behaviour import (
    DESCRIPTION_FRESHNESS_DAYS,
    DESCRIPTION_LOCK_TTL,
)
from analyst.runner import run_agent
from scraper.models import Asset

logger = logging.getLogger(__name__)


def _lock_key(ticker: str) -> str:
    return f"description:{ticker}:lock"


def _run_agent(prompt: str) -> str:
    return run_agent(description_agent, prompt)


def generate_description(asset: Asset) -> str | None:
    """Generate and persist a brief company description for the asset."""
    # Skip if fresh (less than 90 days old)
    if (
        asset.description
        and asset.description_updated_at
        and (timezone.now() - asset.description_updated_at).days
        <= DESCRIPTION_FRESHNESS_DAYS
    ):
        return asset.description

    lock_key = _lock_key(asset.ticker)
    if not cache.add(lock_key, True, DESCRIPTION_LOCK_TTL):
        logger.debug("Description generation for %s already in progress", asset.ticker)
        return None

    try:
        prompt = (
            f"Write a brief description of {asset.name} (ticker: {asset.ticker}). "
            f"Search the web first to ensure you have the latest accurate information."
        )
        logger.info("Generating description for %s...", asset.ticker)
        description = _run_agent(prompt)

        # Persist to DB
        asset.description = description
        asset.description_updated_at = timezone.now()
        asset.save(update_fields=["description", "description_updated_at"])
        return description
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate description for %s", asset.ticker)
        return None
    finally:
        cache.delete(lock_key)
