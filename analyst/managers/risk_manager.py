import asyncio
import logging

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.provider import get_model_provider
from analyst.agents.risk_agent import (
    RiskAssessment,
    risk_agent,
)
from analyst.app_behaviour import (
    MAX_AGENT_TURNS,
    RISK_DATA_TTL,
    RISK_FRESHNESS_TTL,
    RISK_LOCK_TTL,
    cache_key,
)
from analyst.grounding import agent_grounding, compute_label
from analyst.utils import asset_label
from scraper.models import Asset

logger = logging.getLogger(__name__)


def _cache_keys(ticker: str) -> tuple[str, str, str]:
    return (
        cache_key("report", "risk", ticker, "data"),
        cache_key("report", "risk", ticker, "fresh"),
        cache_key("report", "risk", ticker, "lock"),
    )


def _run_agent(label: str) -> RiskAssessment:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    prompt = f"Assess the external risk profile for {label}."
    result = asyncio.run(
        Runner.run(
            risk_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_risk(asset: Asset) -> dict | None:
    """Return cached external risk assessment, regenerating when stale."""
    data_key, fresh_key, lock_key = _cache_keys(asset.ticker)

    existing = cache.get(data_key)

    if existing and cache.get(fresh_key):
        logger.debug("External risk for %s served from cache (fresh)", asset.ticker)
        return existing

    if not cache.add(lock_key, True, RISK_LOCK_TTL):
        logger.debug(
            "External risk generation for %s already in progress", asset.ticker
        )
        return existing

    try:
        logger.info("Generating external risk for %s...", asset.ticker)

        assessment = _run_agent(asset_label(asset))
        data = assessment.model_dump()
        data["label"] = compute_label("risk", data["score"])
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, RISK_DATA_TTL)
        cache.set(fresh_key, True, RISK_FRESHNESS_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate external risk for %s", asset.ticker)
        cache.delete(lock_key)
        return existing
