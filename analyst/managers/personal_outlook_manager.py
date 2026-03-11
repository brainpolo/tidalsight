import hashlib
import logging
from collections import Counter

from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.utils import timezone
from openai import APIStatusError

from analyst.agents.personal_outlook import PersonalOutlook, personal_outlook_agent
from analyst.app_behaviour import (
    OUTLOOK_DATA_TTL,
    OUTLOOK_FRESHNESS_TTL,
    OUTLOOK_LOCK_TTL,
    cache_key,
)
from analyst.managers.digest_manager import DIGEST_DATA_KEY
from analyst.managers.overall_assessment_manager import (
    _base_cache_keys as overall_base_cache_keys,
)
from analyst.managers.overall_assessment_manager import (
    compute_verdict,
)
from analyst.runner import run_agent
from core.models import UserAsset

logger = logging.getLogger(__name__)


def _cache_keys(user_id: int) -> tuple[str, str, str]:
    return (
        cache_key("report", "outlook", user_id, "data"),
        cache_key("report", "outlook", user_id, "fresh"),
        cache_key("report", "outlook", user_id, "lock"),
    )


def _fetch_watchlist_data(user_id: int) -> tuple[dict | None, list[dict]]:
    """Gather market digest + watchlist asset summaries from cache."""
    digest = cache.get(DIGEST_DATA_KEY)

    asset_summaries = []
    for ua in (
        UserAsset.objects.filter(user_id=user_id, in_watchlist=True)
        .select_related("asset")
        .only(
            "note",
            "price_target",
            "asset__ticker",
            "asset__name",
            "asset__asset_class",
            "asset__report_card_score",
            "asset__target_price",
        )
    ):
        asset = ua.asset
        # Read cached overall assessment for richer data (key_drivers, key_risks)
        overall_key, _ = overall_base_cache_keys(asset.ticker)
        cached_overall = cache.get(overall_key)

        summary = {
            "ticker": asset.ticker,
            "name": asset.name,
            "asset_class": asset.get_asset_class_display(),
            "score": asset.report_card_score,
            "verdict": compute_verdict(asset.report_card_score)
            if asset.report_card_score
            else None,
            "target_price": float(asset.target_price) if asset.target_price else None,
            "key_drivers": [],
            "key_risks": [],
            "user_note": ua.note or None,
            "user_price_target": float(ua.price_target) if ua.price_target else None,
        }

        if cached_overall:
            summary["key_drivers"] = cached_overall.get("key_drivers", [])[:3]
            summary["key_risks"] = cached_overall.get("key_risks", [])[:3]
            summary["justification"] = cached_overall.get("justification", "")

        asset_summaries.append(summary)

    return digest, asset_summaries


def _build_prompt(digest: dict | None, summaries: list[dict]) -> str:
    sections = []

    # Market context
    if digest:
        lines = ["## Market Context"]
        if digest.get("headline"):
            lines.append(f"**Headline**: {digest['headline']}")
        for theme in digest.get("themes", []):
            lines.append(f"- {theme}")
        if digest.get("sentiment"):
            lines.append(
                f"**Sentiment**: {digest['sentiment']} — {digest.get('sentiment_reason', '')}"
            )
        if digest.get("outlook"):
            lines.append(f"**Outlook**: {digest['outlook']}")
        sections.append("\n".join(lines))
    else:
        sections.append("## Market Context\nNo market digest available currently.")

    # Per-asset summaries
    lines = ["## Your Watchlist"]
    scored = [s for s in summaries if s["score"]]
    pending = [s for s in summaries if not s["score"]]

    for s in scored:
        lines.append(f"\n### ${s['ticker']} — {s['name']} ({s['asset_class']})")
        lines.append(f"- **Score**: {s['score']}/30 — **Verdict**: {s['verdict']}")
        if s["target_price"]:
            lines.append(f"- **AI Target Price**: ${s['target_price']:,.2f}")
        if s["key_drivers"]:
            lines.append(f"- **Key Drivers**: {'; '.join(s['key_drivers'])}")
        if s["key_risks"]:
            lines.append(f"- **Key Risks**: {'; '.join(s['key_risks'])}")
        if s["user_note"]:
            lines.append(f"- **User Note**: {s['user_note']}")
        if s["user_price_target"]:
            lines.append(f"- **User Price Target**: ${s['user_price_target']:,.2f}")

    if pending:
        lines.append("\n### Pending Analysis")
        for s in pending:
            lines.append(
                f"- ${s['ticker']} ({s['name']}, {s['asset_class']}) — analysis not yet complete"
            )

    sections.append("\n".join(lines))

    # Portfolio composition
    class_counts = Counter(s["asset_class"] for s in summaries)
    scored_scores = [s["score"] for s in summaries if s["score"]]
    avg_score = (
        round(sum(scored_scores) / len(scored_scores), 1) if scored_scores else 0
    )
    verdict_counts = Counter(s["verdict"] for s in summaries if s["verdict"])

    lines = ["## Portfolio Composition"]
    lines.append(f"- **Total holdings**: {len(summaries)}")
    lines.append(
        f"- **Asset mix**: {', '.join(f'{count} {cls}' for cls, count in class_counts.most_common())}"
    )
    if scored_scores:
        lines.append(f"- **Average score**: {avg_score}/30")
        lines.append(
            f"- **Verdicts**: {', '.join(f'{count} {v}' for v, count in verdict_counts.most_common())}"
        )
    sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _source_fingerprint(digest: dict | None, summaries: list[dict]) -> str:
    parts = []
    if digest:
        parts.append(f"digest:{digest.get('source_hash', '')}")
    for s in sorted(summaries, key=lambda x: x["ticker"]):
        parts.append(f"{s['ticker']}:{s['score']}:{s['verdict']}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def _run_agent(prompt: str) -> PersonalOutlook:
    return run_agent(personal_outlook_agent, prompt)


def get_personal_outlook(user_id: int) -> dict | None:
    """Return cached personal outlook, regenerating if stale."""
    data_key, fresh_key, lock_key = _cache_keys(user_id)
    existing = cache.get(data_key)

    if existing and cache.get(fresh_key):
        logger.debug("Personal outlook for user %s served from cache (fresh)", user_id)
        return existing

    if not cache.add(lock_key, True, OUTLOOK_LOCK_TTL):
        logger.debug(
            "Personal outlook for user %s already generating, serving stale", user_id
        )
        return existing

    try:
        digest, summaries = _fetch_watchlist_data(user_id)
        if not summaries:
            logger.info("No watchlist items for user %s, skipping outlook", user_id)
            return None

        fingerprint = _source_fingerprint(digest, summaries)
        if existing and existing.get("source_hash") == fingerprint:
            logger.debug("Outlook sources unchanged for user %s, refreshing TTL", user_id)
            cache.set(fresh_key, True, OUTLOOK_FRESHNESS_TTL)
            return existing

        prompt = _build_prompt(digest, summaries)
        logger.info(
            "Generating personal outlook for user %s (%d assets)...",
            user_id,
            len(summaries),
        )

        try:
            outlook = _run_agent(prompt)
        except (
            ConnectionError,
            RuntimeError,
            ValueError,
            TimeoutError,
            ModelBehaviorError,
            APIStatusError,
        ):
            logger.exception(
                "Failed to generate personal outlook for user %s. Prompt (%d chars):\n%s",
                user_id,
                len(prompt),
                prompt[:2000],
            )
            return existing

        data = outlook.model_dump()
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, OUTLOOK_DATA_TTL)
        cache.set(fresh_key, True, OUTLOOK_FRESHNESS_TTL)

        return data
    finally:
        cache.delete(lock_key)
