import asyncio
import logging

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.description_agent import description_agent
from analyst.agents.provider import get_model_provider
from analyst.app_behaviour import (
    DESCRIPTION_FRESHNESS_DAYS,
    DESCRIPTION_LOCK_TTL,
    MAX_AGENT_TURNS,
)
from analyst.grounding import agent_grounding
from scraper.models import Asset

logger = logging.getLogger(__name__)


def _lock_key(ticker: str) -> str:
    return f"description:{ticker}:lock"


def _run_agent(prompt: str) -> str:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            description_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


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
        logger.info("Description generation for %s already in progress", asset.ticker)
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
        cache.delete(lock_key)
        return description
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate description for %s", asset.ticker)
        cache.delete(lock_key)
        return None
