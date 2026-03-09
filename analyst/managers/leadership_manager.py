import asyncio
import hashlib
import logging
from datetime import datetime

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.leadership_agent import LeadershipAssessment, leadership_agent
from analyst.agents.provider import get_model_provider
from analyst.grounding import agent_grounding
from analyst.app_behaviour import (
    LEADERSHIP_DATA_TTL,
    LEADERSHIP_FRESHNESS_TTL,
    LEADERSHIP_LOCK_TTL,
    MAX_AGENT_TURNS,
)
from scraper.models import Asset

logger = logging.getLogger(__name__)


def _cache_keys(user_id: int, ticker: str) -> tuple[str, str]:
    return (
        f"leadership:{user_id}:{ticker}:data",
        f"leadership:{user_id}:{ticker}:lock",
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
        if age_seconds < LEADERSHIP_FRESHNESS_TTL:
            return True
    return False


def _build_prompt(
    asset: Asset,
    user_note: str,
    price_target: float | None,
) -> str:
    """Build prompt with company info and user context. Agent does its own research."""
    lines = [
        f"Assess the leadership quality and hiring momentum for "
        f"{asset.ticker} ({asset.name})."
    ]
    if user_note:
        lines.append(f"\n## Investor's Notes\n{user_note}")
    if price_target is not None:
        lines.append(f"\n## Investor's Price Target: ${price_target:,.2f}")
    return "\n".join(lines)


def _run_agent(prompt: str) -> LeadershipAssessment:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            leadership_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_leadership(
    asset: Asset,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> dict | None:
    """Return cached leadership assessment, regenerating when stale or inputs change."""
    data_key, lock_key = _cache_keys(user_id, asset.ticker)

    existing = cache.get(data_key)

    fingerprint = _source_fingerprint(user_note, price_target)

    if existing and _is_cache_valid(existing, fingerprint):
        logger.info(
            "Leadership for %s (user %s) served from cache", asset.ticker, user_id
        )
        return existing

    if not cache.add(lock_key, True, LEADERSHIP_LOCK_TTL):
        logger.info(
            "Leadership generation for %s already in progress", asset.ticker
        )
        return existing

    try:
        prompt = _build_prompt(asset, user_note, price_target)
        logger.info(
            "Generating Leadership for %s (user %s)...", asset.ticker, user_id
        )

        assessment = _run_agent(prompt)
        data = assessment.model_dump()
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, LEADERSHIP_DATA_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate Leadership for %s", asset.ticker)
        cache.delete(lock_key)
        return existing
