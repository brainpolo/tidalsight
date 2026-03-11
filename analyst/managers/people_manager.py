import hashlib
import logging
from datetime import datetime

from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.people_agent import PeopleAssessment, people_agent
from analyst.app_behaviour import (
    PEOPLE_DATA_TTL,
    PEOPLE_FRESHNESS_TTL,
    PEOPLE_LOCK_TTL,
    REVISION_LOCK_TTL,
    cache_key,
)
from analyst.grounding import compute_label
from analyst.managers.revision_manager import revise_assessment
from analyst.runner import run_agent
from analyst.utils import asset_label
from scraper.models import Asset

logger = logging.getLogger(__name__)


def _base_cache_keys(ticker: str) -> tuple[str, str]:
    return (
        cache_key("report", "people", "base", ticker, "data"),
        cache_key("report", "people", "base", ticker, "lock"),
    )


def _revision_cache_keys(user_id: int, ticker: str) -> tuple[str, str]:
    return (
        cache_key("report", "people", "rev", user_id, ticker, "data"),
        cache_key("report", "people", "rev", user_id, ticker, "lock"),
    )


def _base_source_fingerprint() -> str:
    """Base has no varying inputs — agent does its own web research."""
    return hashlib.md5(b"base").hexdigest()


def _revision_source_fingerprint(
    base_hash: str, user_note: str, price_target: float | None
) -> str:
    """Hash base assessment + user inputs for revision cache validity."""
    parts = [f"base:{base_hash}", f"note:{user_note}", f"target:{price_target}"]
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
        if age_seconds < PEOPLE_FRESHNESS_TTL:
            return True
    return False


def _build_prompt(asset: Asset) -> str:
    """Build prompt with company info (no user context). Agent does its own research."""
    return (
        f"Assess the people quality — leadership, talent, hiring practices, "
        f"and organisational culture — for {asset_label(asset)}."
    )


def _run_agent(prompt: str) -> PeopleAssessment:
    return run_agent(people_agent, prompt)


def get_base_people(asset: Asset) -> dict | None:
    """Return cached base people assessment (no user context), regenerating when stale."""
    data_key, lock_key = _base_cache_keys(asset.ticker)

    existing = cache.get(data_key)

    fingerprint = _base_source_fingerprint()

    if existing and _is_cache_valid(existing, fingerprint):
        logger.debug("Base people for %s served from cache", asset.ticker)
        return existing

    if not cache.add(lock_key, True, PEOPLE_LOCK_TTL):
        logger.debug("Base people generation for %s already in progress", asset.ticker)
        return existing

    try:
        prompt = _build_prompt(asset)
        logger.info("Generating base people assessment for %s...", asset.ticker)

        assessment = _run_agent(prompt)
        data = assessment.model_dump()
        data["label"] = compute_label("people", data["score"])
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, PEOPLE_DATA_TTL)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception(
            "Failed to generate base people assessment for %s", asset.ticker
        )
        return existing
    finally:
        cache.delete(lock_key)


def get_people(
    asset: Asset,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> dict | None:
    """Return effective people assessment: revised if user has notes, otherwise base."""
    base = get_base_people(asset)
    if base is None:
        return None

    # No user context → return base directly
    if not user_note and price_target is None:
        return base

    # Check revision cache
    rev_data_key, rev_lock_key = _revision_cache_keys(user_id, asset.ticker)
    existing_rev = cache.get(rev_data_key)

    rev_fp = _revision_source_fingerprint(
        base.get("source_hash", ""), user_note, price_target
    )

    if existing_rev and existing_rev.get("source_hash") == rev_fp:
        logger.debug(
            "Revised people for %s (user %s) served from cache",
            asset.ticker,
            user_id,
        )
        return existing_rev

    if not cache.add(rev_lock_key, True, REVISION_LOCK_TTL):
        logger.debug(
            "People revision for %s (user %s) already in progress",
            asset.ticker,
            user_id,
        )
        return existing_rev or base

    try:
        logger.info(
            "Generating people revision for %s (user %s)...",
            asset.ticker,
            user_id,
        )
        revised = revise_assessment("people", base, user_note, price_target, asset)
        revised["source_hash"] = rev_fp
        revised["generated_at"] = timezone.now().isoformat()
        revised["is_revised"] = True

        cache.set(rev_data_key, revised, PEOPLE_DATA_TTL)
        return revised
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception(
            "Failed to revise people for %s (user %s), falling back to base",
            asset.ticker,
            user_id,
        )
        return existing_rev or base
    finally:
        cache.delete(rev_lock_key)
