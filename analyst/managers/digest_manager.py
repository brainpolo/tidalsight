import asyncio
import logging

from agents import RunConfig, Runner
from django.core.cache import cache
from django.db.models import Prefetch
from django.utils import timezone

from analyst.agents.market_digest import MarketDigest, market_digest_agent
from analyst.agents.provider import get_model_provider
from analyst.app_behaviour import (
    DIGEST_DATA_TTL,
    DIGEST_FRESHNESS_TTL,
    DIGEST_LOCK_TTL,
    HN_COMMENT_BODY_TRUNCATION,
    HN_COMMENTS_PER_POST_FOR_DIGEST,
    HN_POSTS_FOR_DIGEST,
    NEWS_ARTICLE_DESCRIPTION_TRUNCATION,
    NEWS_ARTICLES_FOR_DIGEST,
    REDDIT_COMMENT_BODY_TRUNCATION,
    REDDIT_COMMENTS_PER_POST_FOR_DIGEST,
    REDDIT_POST_BODY_TRUNCATION,
    REDDIT_POSTS_FOR_DIGEST,
)
from scraper.models import HNComment, HNPost, NewsArticle, RedditComment, RedditPost

logger = logging.getLogger(__name__)

DIGEST_DATA_KEY = "market_digest_data"
DIGEST_FRESH_KEY = "market_digest_fresh"
DIGEST_LOCK_KEY = "market_digest_lock"


def _build_reddit_section() -> str:
    posts = list(
        RedditPost.objects.order_by("-posted_at").prefetch_related(
            Prefetch(
                "comments",
                queryset=RedditComment.objects.order_by("-score"),
            ),
        )[:REDDIT_POSTS_FOR_DIGEST]
    )
    if not posts:
        return ""

    lines = ["## Reddit Discussions"]
    for p in posts:
        lines.append(
            f"[r/{p.subreddit}] (score:{p.score}, comments:{p.num_comments}) {p.title}"
        )
        if p.body:
            lines.append(f"  {p.body[:REDDIT_POST_BODY_TRUNCATION]}")

        for c in p.comments.all()[:REDDIT_COMMENTS_PER_POST_FOR_DIGEST]:
            lines.append(
                f"    > {c.author} (score:{c.score}): {c.body[:REDDIT_COMMENT_BODY_TRUNCATION]}"
            )

    return "\n".join(lines)


def _build_hn_section() -> str:
    posts = list(
        HNPost.objects.order_by("-posted_at").prefetch_related(
            Prefetch(
                "comments",
                queryset=HNComment.objects.order_by("-posted_at"),
            ),
        )[:HN_POSTS_FOR_DIGEST]
    )
    if not posts:
        return ""

    lines = ["## Hacker News Discussions"]
    for p in posts:
        lines.append(f"[HN] (score:{p.score}, comments:{p.num_comments}) {p.title}")

        for c in p.comments.all()[:HN_COMMENTS_PER_POST_FOR_DIGEST]:
            lines.append(f"    > {c.author}: {c.body[:HN_COMMENT_BODY_TRUNCATION]}")

    return "\n".join(lines)


def _build_news_section() -> str:
    articles = list(
        NewsArticle.objects.order_by("-published_at")[:NEWS_ARTICLES_FOR_DIGEST]
    )
    if not articles:
        return ""

    lines = ["## News Articles"]
    for a in articles:
        date = a.published_at.strftime("%Y-%m-%d") if a.published_at else "unknown"
        lines.append(f"[{a.source}, {date}] {a.title}")
        if a.description:
            lines.append(f"  {a.description[:NEWS_ARTICLE_DESCRIPTION_TRUNCATION]}")

    return "\n".join(lines)


def _build_prompt() -> str:
    sections = [
        _build_reddit_section(),
        _build_hn_section(),
        _build_news_section(),
    ]
    non_empty = [s for s in sections if s]
    if not non_empty:
        return ""
    return "\n\n".join(non_empty)


def _run_agent(prompt: str) -> MarketDigest:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(market_digest_agent, input=prompt, run_config=config)
    )
    return result.final_output


def get_market_digest() -> dict | None:
    existing = cache.get(DIGEST_DATA_KEY)

    # If the digest is still fresh, return it immediately
    if existing and cache.get(DIGEST_FRESH_KEY):
        logger.info("Market digest served from cache (fresh)")
        return existing

    # Digest is stale or missing — try to regenerate
    if not cache.add(DIGEST_LOCK_KEY, True, DIGEST_LOCK_TTL):
        logger.info("Market digest generation already in progress, serving stale")
        return existing

    prompt = _build_prompt()
    if not prompt:
        logger.warning("No data from any source, skipping digest")
        cache.delete(DIGEST_LOCK_KEY)
        return existing

    logger.info("Generating market digest from %d posts...", prompt.count("\n") + 1)

    try:
        digest = _run_agent(prompt)
    except ConnectionError, RuntimeError, ValueError, TimeoutError:
        logger.exception("Failed to generate market digest")
        cache.delete(DIGEST_LOCK_KEY)
        return existing

    data = digest.model_dump()
    data["generated_at"] = timezone.now().isoformat()
    logger.info("Market digest generated, freshness TTL %ds", DIGEST_FRESHNESS_TTL)
    cache.set(DIGEST_DATA_KEY, data, DIGEST_DATA_TTL)
    cache.set(DIGEST_FRESH_KEY, True, DIGEST_FRESHNESS_TTL)
    cache.delete(DIGEST_LOCK_KEY)
    return data
