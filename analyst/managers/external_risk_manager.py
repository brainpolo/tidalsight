import asyncio
import logging

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.external_risk_agent import ExternalRiskAssessment, external_risk_agent
from analyst.agents.provider import get_model_provider
from analyst.grounding import agent_grounding
from analyst.app_behaviour import (
    EXTERNAL_RISK_DATA_TTL,
    EXTERNAL_RISK_FRESHNESS_TTL,
    EXTERNAL_RISK_LOCK_TTL,
    MAX_AGENT_TURNS,
)
from scraper.models import Asset

logger = logging.getLogger(__name__)


def _cache_keys(ticker: str) -> tuple[str, str, str]:
    return (
        f"external_risk:{ticker}:data",
        f"external_risk:{ticker}:fresh",
        f"external_risk:{ticker}:lock",
    )


def _run_agent(ticker: str, company_name: str) -> ExternalRiskAssessment:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    prompt = f"Assess the external risk profile for {ticker} ({company_name})."
    result = asyncio.run(
        Runner.run(
            external_risk_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_external_risk(asset: Asset) -> dict | None:
    """Return cached external risk assessment, regenerating when stale."""
    data_key, fresh_key, lock_key = _cache_keys(asset.ticker)

    existing = cache.get(data_key)

    if existing and cache.get(fresh_key):
        logger.info("External risk for %s served from cache (fresh)", asset.ticker)
        return existing

    if not cache.add(lock_key, True, EXTERNAL_RISK_LOCK_TTL):
        logger.info(
            "External risk generation for %s already in progress", asset.ticker
        )
        return existing

    try:
        logger.info("Generating external risk for %s...", asset.ticker)

        assessment = _run_agent(asset.ticker, asset.name)
        data = assessment.model_dump()
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, EXTERNAL_RISK_DATA_TTL)
        cache.set(fresh_key, True, EXTERNAL_RISK_FRESHNESS_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate external risk for %s", asset.ticker)
        cache.delete(lock_key)
        return existing
