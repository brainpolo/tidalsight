import asyncio
import hashlib
import logging
from datetime import datetime

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.provider import get_model_provider
from analyst.agents.valuation_agent import ValuationAssessment, valuation_agent
from analyst.app_behaviour import (
    MAX_AGENT_TURNS,
    REVISION_LOCK_TTL,
    VALUATION_DATA_TTL,
    VALUATION_FRESHNESS_TTL,
    VALUATION_LOCK_TTL,
    cache_key,
)
from analyst.grounding import agent_grounding, compute_label
from analyst.managers.revision_manager import revise_assessment
from core.managers.valuation_manager import compute_rsi, compute_valuations
from core.templatetags.formatting import abbreviate
from scraper.models import Asset, Fundamental

logger = logging.getLogger(__name__)

VALUATION_FIELDS = [
    "eps",
    "pe_ratio",
    "dividend_yield",
    "market_cap",
    "revenue",
    "fifty_two_week_high",
    "fifty_two_week_low",
    "price_to_book",
    "profit_margin",
    "revenue_growth",
    "earnings_growth",
]


def _base_cache_keys(ticker: str) -> tuple[str, str]:
    return (
        cache_key("report", "valuation", "base", ticker, "data"),
        cache_key("report", "valuation", "base", ticker, "lock"),
    )


def _revision_cache_keys(user_id: int, ticker: str) -> tuple[str, str]:
    return (
        cache_key("report", "valuation", "rev", user_id, ticker, "data"),
        cache_key("report", "valuation", "rev", user_id, ticker, "lock"),
    )


def _base_source_fingerprint(
    fundamental: Fundamental,
    latest_close: float,
    rsi: float | None = None,
) -> str:
    """Hash valuation inputs (excluding user context) to detect changes."""
    parts = []
    for field in VALUATION_FIELDS:
        val = getattr(fundamental, field, None)
        parts.append(f"{field}:{val}")
    parts.append(f"close:{latest_close}")
    parts.append(f"rsi:{rsi}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()


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
        if age_seconds < VALUATION_FRESHNESS_TTL:
            return True
    return False


def _build_prompt(
    asset: Asset,
    fundamental: Fundamental,
    latest_price,
    valuations: list[dict],
    rsi: float | None = None,
) -> str:
    """Build markdown prompt with valuation data and fundamentals (no user context)."""
    current = float(latest_price.close)
    lines = [f"# Valuation Data for {asset.ticker} ({asset.name})\n"]
    lines.append(f"**Current Price**: ${current:,.2f}")
    if rsi is not None:
        lines.append(f"**RSI (14-day)**: {rsi}")
    lines.append("")

    # Pre-computed valuation models
    if valuations:
        lines.append("## Fair Value Estimates\n")
        for v in valuations:
            direction = "above" if v["delta_pct"] > 0 else "below"
            lines.append(
                f"- **{v['name']}**: ${v['value']:,.2f} "
                f"({abs(v['delta_pct']):.1f}% {direction} current price) — {v['description']}"
            )
        lines.append("")

    # Key fundamentals
    lines.append("## Key Fundamentals\n")
    field_labels = {
        "pe_ratio": ("P/E Ratio", "", False),
        "price_to_book": ("Price-to-Book", "", False),
        "eps": ("EPS", "$", False),
        "dividend_yield": ("Dividend Yield", "", False, "%"),
        "market_cap": ("Market Cap", "$", True),
        "revenue": ("Revenue", "$", True),
        "profit_margin": ("Profit Margin", "", False, "%"),
        "revenue_growth": ("Revenue Growth (YoY)", "", False, "%"),
        "earnings_growth": ("Earnings Growth (YoY)", "", False, "%"),
    }
    for field, meta in field_labels.items():
        raw = getattr(fundamental, field, None)
        if raw is None:
            continue
        label = meta[0]
        prefix = meta[1]
        use_abbrev = meta[2] if len(meta) > 2 else False
        suffix = meta[3] if len(meta) > 3 else ""
        if use_abbrev:
            display = f"{prefix}{abbreviate(raw)}"
        else:
            display = f"{prefix}{float(raw):,.2f}{suffix}"
        lines.append(f"- **{label}**: {display}")

    return "\n".join(lines)


def _run_agent(prompt: str) -> ValuationAssessment:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            valuation_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_base_valuation(asset: Asset) -> dict | None:
    """Return cached base valuation (no user context), regenerating when inputs change."""
    data_key, lock_key = _base_cache_keys(asset.ticker)

    existing = cache.get(data_key)

    fundamental = asset.fundamentals.first()
    if not fundamental:
        logger.debug("No fundamentals for %s, skipping valuation", asset.ticker)
        return None

    latest_price = asset.prices.first()
    if not latest_price:
        logger.debug("No price data for %s, skipping valuation", asset.ticker)
        return None

    rsi = compute_rsi(asset)

    fingerprint = _base_source_fingerprint(fundamental, float(latest_price.close), rsi)

    if existing and _is_cache_valid(existing, fingerprint):
        logger.debug("Base valuation for %s served from cache", asset.ticker)
        return existing

    if not cache.add(lock_key, True, VALUATION_LOCK_TTL):
        logger.debug(
            "Base valuation generation for %s already in progress", asset.ticker
        )
        return existing

    try:
        valuations = compute_valuations(asset, fundamental, latest_price)
        if len(valuations) < 2:
            logger.debug(
                "Only %d valuation models for %s, skipping",
                len(valuations),
                asset.ticker,
            )
            cache.delete(lock_key)
            return None

        prompt = _build_prompt(asset, fundamental, latest_price, valuations, rsi)
        logger.info("Generating base valuation for %s...", asset.ticker)

        assessment = _run_agent(prompt)
        data = assessment.model_dump()
        data["label"] = compute_label("valuation", data["score"])
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, VALUATION_DATA_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate base valuation for %s", asset.ticker)
        cache.delete(lock_key)
        return existing


def get_valuation(
    asset: Asset,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> dict | None:
    """Return effective valuation: revised if user has notes, otherwise base."""
    base = get_base_valuation(asset)
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
            "Revised valuation for %s (user %s) served from cache",
            asset.ticker,
            user_id,
        )
        return existing_rev

    if not cache.add(rev_lock_key, True, REVISION_LOCK_TTL):
        logger.debug(
            "Valuation revision for %s (user %s) already in progress",
            asset.ticker,
            user_id,
        )
        return existing_rev or base

    try:
        logger.info(
            "Generating valuation revision for %s (user %s)...", asset.ticker, user_id
        )
        revised = revise_assessment("valuation", base, user_note, price_target, asset)
        revised["source_hash"] = rev_fp
        revised["generated_at"] = timezone.now().isoformat()
        revised["is_revised"] = True

        cache.set(rev_data_key, revised, VALUATION_DATA_TTL)
        cache.delete(rev_lock_key)
        return revised
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception(
            "Failed to revise valuation for %s (user %s), falling back to base",
            asset.ticker,
            user_id,
        )
        cache.delete(rev_lock_key)
        return existing_rev or base
