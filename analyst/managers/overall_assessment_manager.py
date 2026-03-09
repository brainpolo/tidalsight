import asyncio
import hashlib
import json
import logging

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone

from analyst.agents.overall_assessment_agent import (
    OverallAssessment,
    overall_assessment_agent,
)
from analyst.agents.provider import get_model_provider
from analyst.app_behaviour import (
    MAX_AGENT_TURNS,
    OVERALL_ASSESSMENT_DATA_TTL,
    OVERALL_ASSESSMENT_LOCK_TTL,
)
from analyst.grounding import agent_grounding
from scraper.models import Asset

logger = logging.getLogger(__name__)

# Fields excluded from fingerprint to avoid self-referential invalidation
_META_FIELDS = {"source_hash", "generated_at"}

# Deterministic verdict ranges (total score out of 30)
_VERDICT_RANGES = [
    (10, "Strong Sell"),
    (14, "Sell"),
    (23, "Hold"),
    (26, "Buy"),
    (30, "Strong Buy"),
]


def compute_verdict(total_score: float) -> str:
    """Map a total score (0-30) to a deterministic recommendation."""
    for threshold, label in _VERDICT_RANGES:
        if total_score <= threshold:
            return label
    return "Strong Buy"


def _cache_keys(user_id: int, ticker: str) -> tuple[str, str]:
    return (
        f"overall_assessment:{user_id}:{ticker}:data",
        f"overall_assessment:{user_id}:{ticker}:lock",
    )


def _source_fingerprint(sections: dict[str, dict]) -> str:
    """Hash all 6 section results to detect any change."""
    parts = []
    for name in sorted(sections):
        filtered = {k: v for k, v in sections[name].items() if k not in _META_FIELDS}
        parts.append(f"{name}:{json.dumps(filtered, sort_keys=True, default=str)}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def _is_cache_valid(existing: dict, fingerprint: str) -> bool:
    """Pure fingerprint comparison — no time-based freshness."""
    return existing.get("source_hash") == fingerprint


def _build_prompt(
    asset: Asset,
    current_price: float,
    total_score: float,
    verdict: str,
    sections: dict[str, dict],
) -> str:
    """Build structured markdown prompt from all 6 sections."""
    lines = [
        f"# Overall Assessment for {asset.ticker} ({asset.name})\n",
        f"**Current Price**: ${current_price:,.2f}",
        f"**Total Score**: {total_score} / 30",
        f"**Recommendation**: {verdict}\n",
    ]

    # Hygiene Factors
    lines.append("## Hygiene Factors (necessary conditions)\n")
    for key, label in [
        ("financial_health", "Financial Health"),
        ("sentiment", "Sentiment"),
        ("external_risk", "External Risk"),
    ]:
        section = sections.get(key, {})
        lines.append(f"### {label}")
        lines.append(f"- **Score**: {section.get('score', 'N/A')} / 5")
        lines.append(f"- **Label**: {section.get('label', 'N/A')}")
        lines.append(f"- **Brief**: {section.get('brief', 'N/A')}")
        _append_list_field(lines, section, "strengths", "Strengths")
        _append_list_field(lines, section, "concerns", "Concerns")
        _append_list_field(lines, section, "key_themes", "Key Themes")
        _append_list_field(lines, section, "risk_factors", "Risk Factors")
        lines.append("")

    # Motivators
    lines.append("## Motivators (sufficient conditions for alpha)\n")
    for key, label in [
        ("valuation", "Valuation"),
        ("product_flywheel", "Product Flywheel"),
        ("leadership", "Leadership"),
    ]:
        section = sections.get(key, {})
        lines.append(f"### {label}")
        lines.append(f"- **Score**: {section.get('score', 'N/A')} / 5")
        lines.append(f"- **Label**: {section.get('label', 'N/A')}")
        lines.append(f"- **Brief**: {section.get('brief', 'N/A')}")
        _append_list_field(lines, section, "bull_cases", "Bull Cases")
        _append_list_field(lines, section, "bear_cases", "Bear Cases")
        _append_list_field(lines, section, "flywheel_strengths", "Flywheel Strengths")
        _append_list_field(lines, section, "moat_risks", "Moat Risks")
        _append_list_field(
            lines, section, "leadership_strengths", "Leadership Strengths"
        )
        _append_list_field(lines, section, "leadership_risks", "Leadership Risks")
        lines.append("")

    return "\n".join(lines)


def _append_list_field(lines: list[str], section: dict, field: str, label: str) -> None:
    """Append a list field to prompt lines if it exists and is non-empty."""
    items = section.get(field)
    if items:
        lines.append(f"- **{label}**: {', '.join(str(i) for i in items)}")


def _run_agent(prompt: str) -> OverallAssessment:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            overall_assessment_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_overall_assessment(
    asset: Asset,
    user_id: int,
    sections: dict[str, dict],
) -> dict | None:
    """Return cached overall assessment, regenerating when any section changes."""
    if len(sections) < 6:
        logger.info(
            "Only %d/6 sections for %s, skipping overall", len(sections), asset.ticker
        )
        return None

    data_key, lock_key = _cache_keys(user_id, asset.ticker)
    existing = cache.get(data_key)

    fingerprint = _source_fingerprint(sections)

    if existing and _is_cache_valid(existing, fingerprint):
        logger.info(
            "Overall assessment for %s (user %s) served from cache",
            asset.ticker,
            user_id,
        )
        return existing

    if not cache.add(lock_key, True, OVERALL_ASSESSMENT_LOCK_TTL):
        logger.info(
            "Overall assessment generation for %s already in progress", asset.ticker
        )
        return existing

    try:
        latest_price = asset.prices.first()
        current_price = float(latest_price.close) if latest_price else 0.0

        total_score = round(sum(s.get("score", 0) for s in sections.values()), 1)
        verdict = compute_verdict(total_score)

        prompt = _build_prompt(asset, current_price, total_score, verdict, sections)
        logger.info(
            "Generating overall assessment for %s (user %s)...", asset.ticker, user_id
        )

        assessment = _run_agent(prompt)
        data = assessment.model_dump()
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, OVERALL_ASSESSMENT_DATA_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate overall assessment for %s", asset.ticker)
        cache.delete(lock_key)
        return existing
