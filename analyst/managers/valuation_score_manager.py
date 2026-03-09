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
    VALUATION_DATA_TTL,
    VALUATION_FRESHNESS_TTL,
    VALUATION_LOCK_TTL,
)
from analyst.grounding import agent_grounding
from core.managers.valuation_manager import compute_valuations
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


def _cache_keys(user_id: int, ticker: str) -> tuple[str, str]:
    return (
        f"valuation:{user_id}:{ticker}:data",
        f"valuation:{user_id}:{ticker}:lock",
    )


def _source_fingerprint(
    fundamental: Fundamental,
    latest_close: float,
    user_note: str,
    price_target: float | None,
) -> str:
    """Hash valuation inputs to detect changes."""
    parts = []
    for field in VALUATION_FIELDS:
        val = getattr(fundamental, field, None)
        parts.append(f"{field}:{val}")
    parts.append(f"close:{latest_close}")
    parts.append(f"note:{user_note}")
    parts.append(f"target:{price_target}")
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
    user_note: str,
    price_target: float | None,
) -> str:
    """Build markdown prompt with valuation data, fundamentals, and user context."""
    current = float(latest_price.close)
    lines = [f"# Valuation Data for {asset.ticker} ({asset.name})\n"]
    lines.append(f"**Current Price**: ${current:,.2f}\n")

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

    # User context
    if user_note:
        lines.append(f"\n## Investor's Notes\n{user_note}")
    if price_target is not None:
        lines.append(f"\n## Investor's Price Target: ${price_target:,.2f}")

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


def get_valuation(
    asset: Asset,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> dict | None:
    """Return cached valuation assessment, regenerating when inputs change or stale."""
    data_key, lock_key = _cache_keys(user_id, asset.ticker)

    existing = cache.get(data_key)

    fundamental = asset.fundamentals.first()
    if not fundamental:
        logger.info("No fundamentals for %s, skipping valuation", asset.ticker)
        return None

    latest_price = asset.prices.first()
    if not latest_price:
        logger.info("No price data for %s, skipping valuation", asset.ticker)
        return None

    fingerprint = _source_fingerprint(
        fundamental, float(latest_price.close), user_note, price_target
    )

    if existing and _is_cache_valid(existing, fingerprint):
        logger.info(
            "Valuation for %s (user %s) served from cache", asset.ticker, user_id
        )
        return existing

    if not cache.add(lock_key, True, VALUATION_LOCK_TTL):
        logger.info("Valuation generation for %s already in progress", asset.ticker)
        return existing

    try:
        valuations = compute_valuations(asset, fundamental, latest_price)
        if len(valuations) < 2:
            logger.info(
                "Only %d valuation models for %s, skipping",
                len(valuations),
                asset.ticker,
            )
            cache.delete(lock_key)
            return None

        prompt = _build_prompt(
            asset, fundamental, latest_price, valuations, user_note, price_target
        )
        logger.info("Generating valuation for %s (user %s)...", asset.ticker, user_id)

        assessment = _run_agent(prompt)
        data = assessment.model_dump()
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, VALUATION_DATA_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate valuation for %s", asset.ticker)
        cache.delete(lock_key)
        return existing
