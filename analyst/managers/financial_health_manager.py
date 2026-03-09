import asyncio
import hashlib
import logging

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.financial_health_agent import (
    FinancialHealthAssessment,
    financial_health_agent,
)
from analyst.agents.provider import get_model_provider
from analyst.app_behaviour import (
    FINANCIAL_HEALTH_DATA_TTL,
    FINANCIAL_HEALTH_LOCK_TTL,
    MAX_AGENT_TURNS,
)
from analyst.grounding import agent_grounding
from core.templatetags.formatting import abbreviate
from scraper.models import Asset, Fundamental

logger = logging.getLogger(__name__)

# Fundamental fields relevant to financial health (excludes valuation-heavy ones)
HEALTH_FIELDS = [
    "revenue",
    "revenue_growth",
    "earnings_growth",
    "profit_margin",
    "eps",
    "free_cash_flow",
    "debt_to_equity",
    "current_ratio",
    "return_on_equity",
    "dividend_yield",
    "market_cap",
    "beta",
    "price_to_book",
]


def _cache_keys(ticker: str) -> tuple[str, str, str]:
    return (
        f"financial_health:{ticker}:data",
        f"financial_health:{ticker}:fresh",
        f"financial_health:{ticker}:lock",
    )


def _source_fingerprint(fundamental: Fundamental) -> str:
    """Hash the fundamental values to detect changes."""
    parts = []
    for field in HEALTH_FIELDS:
        val = getattr(fundamental, field, None)
        parts.append(f"{field}:{val}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def _build_prompt(asset: Asset, fundamental: Fundamental) -> str:
    """Build a markdown prompt from fundamental data."""
    lines = [f"# Financial Data for {asset.ticker} ({asset.name})\n"]

    field_labels = {
        "revenue": ("Revenue", "$", True),
        "revenue_growth": ("Revenue Growth (YoY)", "", False, "%"),
        "earnings_growth": ("Earnings Growth (YoY)", "", False, "%"),
        "profit_margin": ("Profit Margin", "", False, "%"),
        "eps": ("Earnings Per Share (EPS)", "$", False),
        "free_cash_flow": ("Free Cash Flow", "$", True),
        "debt_to_equity": ("Debt-to-Equity Ratio", "", False),
        "current_ratio": ("Current Ratio (liquidity)", "", False),
        "return_on_equity": ("Return on Equity (ROE)", "", False, "%"),
        "dividend_yield": ("Dividend Yield", "", False, "%"),
        "market_cap": ("Market Capitalisation", "$", True),
        "beta": ("Beta (volatility vs market)", "", False),
        "price_to_book": ("Price-to-Book Ratio", "", False),
    }

    for field in HEALTH_FIELDS:
        raw = getattr(fundamental, field, None)
        if raw is None:
            continue

        meta = field_labels.get(field, (field, "", False))
        label = meta[0]
        prefix = meta[1]
        use_abbrev = meta[2] if len(meta) > 2 else False
        suffix = meta[3] if len(meta) > 3 else ""

        if use_abbrev:
            display = f"{prefix}{abbreviate(raw)}"
        else:
            display = f"{prefix}{float(raw):,.2f}{suffix}"

        lines.append(f"- **{label}**: {display}")

    # Add S&P 500 benchmarks for context
    lines.append("\n## S&P 500 Benchmarks (for reference)")
    lines.append("- Profit Margin: ~11%")
    lines.append("- Dividend Yield: ~1.3%")
    lines.append("- ROE: ~18%")
    lines.append("- P/B Ratio: ~4.5")
    lines.append("- Beta: 1.00 (market baseline)")
    lines.append("- Debt/Equity: varies widely by sector (0.5-2.0 typical)")
    lines.append("- Current Ratio: >1.0 is healthy, >2.0 is strong")
    lines.append("- Revenue Growth: S&P 500 average ~5-7% YoY")

    return "\n".join(lines)


def _run_agent(prompt: str) -> FinancialHealthAssessment:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            financial_health_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_financial_health(asset: Asset) -> dict | None:
    """Return cached financial health assessment, regenerating only when fundamentals change."""
    data_key, _, lock_key = _cache_keys(asset.ticker)

    existing = cache.get(data_key)

    # Early check: if fundamentals haven't changed, serve cache immediately
    fundamental = asset.fundamentals.first()
    if not fundamental:
        logger.debug("No fundamentals for %s, skipping health assessment", asset.ticker)
        return None

    fingerprint = _source_fingerprint(fundamental)

    if existing and existing.get("source_hash") == fingerprint:
        logger.debug(
            "Financial health for %s served from cache (unchanged)", asset.ticker
        )
        return existing

    if not cache.add(lock_key, True, FINANCIAL_HEALTH_LOCK_TTL):
        logger.debug(
            "Financial health generation for %s already in progress", asset.ticker
        )
        return existing

    try:
        # Check if at least a few key metrics exist
        available = sum(
            1
            for field in HEALTH_FIELDS
            if getattr(fundamental, field, None) is not None
        )
        if available < 3:
            logger.debug(
                "Only %d fundamental fields for %s, skipping health assessment",
                available,
                asset.ticker,
            )
            cache.delete(lock_key)
            return None

        prompt = _build_prompt(asset, fundamental)
        logger.info(
            "Generating financial health for %s from %d metrics...",
            asset.ticker,
            available,
        )

        assessment = _run_agent(prompt)
        data = assessment.model_dump()
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, FINANCIAL_HEALTH_DATA_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate financial health for %s", asset.ticker)
        cache.delete(lock_key)
        return existing
