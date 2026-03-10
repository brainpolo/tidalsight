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
    cache_key,
)
from analyst.grounding import agent_grounding
from scraper.models import Asset

logger = logging.getLogger(__name__)

# Fields excluded from fingerprint to avoid self-referential invalidation
_META_FIELDS = {"source_hash", "generated_at", "is_revised"}

# Hygiene factors are weighted 1.5×, motivators 1.0× → max 30
HYGIENE_SECTIONS = ("finance", "sentiment", "risk")
MOTIVATOR_SECTIONS = ("valuation", "product", "people")
HYGIENE_WEIGHT = 1.5
MOTIVATOR_WEIGHT = 1.0

# Deterministic verdict ranges (weighted total out of 30)
_VERDICT_RANGES = [
    (12, "Strong Sell"),
    (15, "Sell"),
    (22, "Hold"),
    (26, "Buy"),
    (30, "Strong Buy"),
]


def compute_weighted_score(sections: dict[str, dict]) -> float:
    """Compute weighted total: hygiene × 1.5, motivators × 1.0."""
    total = 0.0
    for key in HYGIENE_SECTIONS:
        total += sections.get(key, {}).get("score", 0) * HYGIENE_WEIGHT
    for key in MOTIVATOR_SECTIONS:
        total += sections.get(key, {}).get("score", 0) * MOTIVATOR_WEIGHT
    return round(total, 1)


def compute_verdict(total_score: float) -> str:
    """Map a weighted total score (0-30) to a deterministic recommendation."""
    for threshold, label in _VERDICT_RANGES:
        if total_score <= threshold:
            return label
    return "Strong Buy"


def _base_cache_keys(ticker: str) -> tuple[str, str]:
    return (
        cache_key("report", "overall", "base", ticker, "data"),
        cache_key("report", "overall", "base", ticker, "lock"),
    )


def _user_cache_keys(user_id: int, ticker: str) -> tuple[str, str]:
    return (
        cache_key("report", "overall", user_id, ticker, "data"),
        cache_key("report", "overall", user_id, ticker, "lock"),
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
        f"**Weighted Total Score**: {total_score} / 30",
        f"**Recommendation**: {verdict}\n",
        "Hygiene factors are weighted 1.5× and motivators 1.0× in the total.\n",
    ]

    # Hygiene Factors
    lines.append("## Hygiene Factors (necessary conditions, weighted 1.5×)\n")
    for key, label in [
        ("finance", "Financial Health"),
        ("sentiment", "Sentiment"),
        ("risk", "External Risk"),
    ]:
        section = sections.get(key, {})
        lines.append(f"### {label}")
        lines.append(f"- **Score**: {section.get('score', 'N/A')} / 4")
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
        ("product", "Product Flywheel"),
        ("people", "People"),
    ]:
        section = sections.get(key, {})
        lines.append(f"### {label}")
        lines.append(f"- **Score**: {section.get('score', 'N/A')} / 4")
        lines.append(f"- **Label**: {section.get('label', 'N/A')}")
        lines.append(f"- **Brief**: {section.get('brief', 'N/A')}")
        _append_list_field(lines, section, "bull_cases", "Bull Cases")
        _append_list_field(lines, section, "bear_cases", "Bear Cases")
        _append_list_field(lines, section, "flywheel_strengths", "Flywheel Strengths")
        _append_list_field(lines, section, "moat_risks", "Moat Risks")
        _append_list_field(
            lines, section, "people_strengths", "People Strengths"
        )
        _append_list_field(lines, section, "people_risks", "People Risks")
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


def _generate_assessment(
    asset: Asset,
    sections: dict[str, dict],
    data_key: str,
    lock_key: str,
    persist_to_db: bool,
    existing: dict | None,
) -> dict | None:
    """Shared generation logic for both base and user overall assessments."""
    if not cache.add(lock_key, True, OVERALL_ASSESSMENT_LOCK_TTL):
        logger.debug(
            "Overall assessment generation for %s already in progress", asset.ticker
        )
        return existing

    try:
        latest_price = asset.prices.first()
        current_price = float(latest_price.close) if latest_price else 0.0

        total_score = compute_weighted_score(sections)
        verdict = compute_verdict(total_score)

        prompt = _build_prompt(asset, current_price, total_score, verdict, sections)
        logger.info("Generating overall assessment for %s...", asset.ticker)

        assessment = _run_agent(prompt)
        fingerprint = _source_fingerprint(sections)
        data = assessment.model_dump()
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, OVERALL_ASSESSMENT_DATA_TTL)
        cache.delete(lock_key)

        if persist_to_db:
            Asset.objects.filter(pk=asset.pk).update(
                report_card_score=round(total_score),
                target_price=assessment.target_price,
                report_card_updated_at=timezone.now(),
            )

        return data
    except (ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError):
        logger.exception("Failed to generate overall assessment for %s", asset.ticker)
        cache.delete(lock_key)
        return existing


def get_base_overall_assessment(
    asset: Asset,
    sections: dict[str, dict],
) -> dict | None:
    """Return base overall assessment (no user influence). Persists score to DB."""
    if len(sections) < 6:
        logger.info(
            "Only %d/6 sections for %s, skipping base overall", len(sections), asset.ticker
        )
        return None

    data_key, lock_key = _base_cache_keys(asset.ticker)
    existing = cache.get(data_key)

    fingerprint = _source_fingerprint(sections)

    if existing and _is_cache_valid(existing, fingerprint):
        logger.debug("Base overall assessment for %s served from cache", asset.ticker)
        return existing

    return _generate_assessment(
        asset, sections, data_key, lock_key, persist_to_db=True, existing=existing
    )


def get_overall_assessment(
    asset: Asset,
    user_id: int,
    sections: dict[str, dict],
) -> dict | None:
    """Return overall assessment. Delegates to base if no sections are revised."""
    if len(sections) < 6:
        logger.info(
            "Only %d/6 sections for %s, skipping overall", len(sections), asset.ticker
        )
        return None

    # Check if any motivator section has been revised by user notes
    has_revisions = any(
        sections.get(key, {}).get("is_revised", False)
        for key in ("valuation", "product", "people")
    )

    if not has_revisions:
        return get_base_overall_assessment(asset, sections)

    # User-specific overall — do NOT persist to DB
    data_key, lock_key = _user_cache_keys(user_id, asset.ticker)
    existing = cache.get(data_key)

    fingerprint = _source_fingerprint(sections)

    if existing and _is_cache_valid(existing, fingerprint):
        logger.debug(
            "User overall assessment for %s (user %s) served from cache",
            asset.ticker,
            user_id,
        )
        return existing

    return _generate_assessment(
        asset, sections, data_key, lock_key, persist_to_db=False, existing=existing
    )
