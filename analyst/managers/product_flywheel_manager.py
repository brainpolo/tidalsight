import asyncio
import hashlib
import logging
from datetime import datetime

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.product_flywheel_agent import (
    ProductFlywheelAssessment,
    product_flywheel_agent,
)
from analyst.agents.provider import get_model_provider
from analyst.app_behaviour import (
    MAX_AGENT_TURNS,
    PRODUCT_FLYWHEEL_DATA_TTL,
    PRODUCT_FLYWHEEL_FRESHNESS_TTL,
    PRODUCT_FLYWHEEL_LOCK_TTL,
)
from analyst.grounding import agent_grounding
from scraper.models import Asset

logger = logging.getLogger(__name__)


def _cache_keys(user_id: int, ticker: str) -> tuple[str, str]:
    return (
        f"product_flywheel:{user_id}:{ticker}:data",
        f"product_flywheel:{user_id}:{ticker}:lock",
    )


def _source_fingerprint(user_note: str, price_target: float | None) -> str:
    """Hash user inputs that affect the assessment."""
    parts = [
        f"note:{user_note}",
        f"target:{price_target}",
    ]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def _is_cache_valid(existing: dict, fingerprint: str) -> bool:
    """Check hybrid invalidation: fingerprint match OR within freshness window."""
    if existing.get("source_hash") == fingerprint:
        return True
    generated_at = existing.get("generated_at")
    if generated_at:
        gen_time = datetime.fromisoformat(generated_at)
        if timezone.is_naive(gen_time):
            gen_time = timezone.make_aware(gen_time)
        age_seconds = (timezone.now() - gen_time).total_seconds()
        if age_seconds < PRODUCT_FLYWHEEL_FRESHNESS_TTL:
            return True
    return False


def _build_prompt(
    asset: Asset,
    user_note: str,
    price_target: float | None,
) -> str:
    """Build prompt with company info and user context. Agent does its own research."""
    lines = [
        f"Assess the product flywheel and competitive moat for "
        f"{asset.ticker} ({asset.name})."
    ]
    if user_note:
        lines.append(f"\n## Investor's Notes\n{user_note}")
    if price_target is not None:
        lines.append(f"\n## Investor's Price Target: ${price_target:,.2f}")
    return "\n".join(lines)


def _run_agent(prompt: str) -> ProductFlywheelAssessment:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            product_flywheel_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_product_flywheel(
    asset: Asset,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> dict | None:
    """Return cached product flywheel assessment, regenerating when stale or inputs change."""
    data_key, lock_key = _cache_keys(user_id, asset.ticker)

    existing = cache.get(data_key)

    fingerprint = _source_fingerprint(user_note, price_target)

    if existing and _is_cache_valid(existing, fingerprint):
        logger.debug(
            "Product Flywheel for %s (user %s) served from cache",
            asset.ticker,
            user_id,
        )
        return existing

    if not cache.add(lock_key, True, PRODUCT_FLYWHEEL_LOCK_TTL):
        logger.debug(
            "Product Flywheel generation for %s already in progress", asset.ticker
        )
        return existing

    try:
        prompt = _build_prompt(asset, user_note, price_target)
        logger.info(
            "Generating Product Flywheel for %s (user %s)...", asset.ticker, user_id
        )

        assessment = _run_agent(prompt)
        data = assessment.model_dump()
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, PRODUCT_FLYWHEEL_DATA_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate Product Flywheel for %s", asset.ticker)
        cache.delete(lock_key)
        return existing
