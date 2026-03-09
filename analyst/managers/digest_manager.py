import asyncio
import hashlib
import logging

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
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
    MAX_AGENT_TURNS,
    NEWS_ARTICLE_DESCRIPTION_TRUNCATION,
    NEWS_ARTICLES_FOR_DIGEST,
    REDDIT_COMMENT_BODY_TRUNCATION,
    REDDIT_COMMENTS_PER_POST_FOR_DIGEST,
    REDDIT_POST_BODY_TRUNCATION,
    REDDIT_POSTS_FOR_DIGEST,
)
from analyst.grounding import agent_grounding
from scraper.models import HNComment, HNPost, NewsArticle, RedditComment, RedditPost

logger = logging.getLogger(__name__)

DIGEST_DATA_KEY = "market_digest_data"
DIGEST_FRESH_KEY = "market_digest_fresh"
DIGEST_LOCK_KEY = "market_digest_lock"


def _source_fingerprint(
    reddit_posts: list[RedditPost],
    hn_posts: list[HNPost],
    news_articles: list[NewsArticle],
) -> str:
    """Compute a hash of the post IDs to detect when sources change."""
    parts = []
    for p in reddit_posts:
        parts.append(f"r:{p.reddit_id}")
    for p in hn_posts:
        parts.append(f"h:{p.hn_id}")
    for a in news_articles:
        parts.append(f"n:{a.url}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def _fetch_sources() -> tuple[list[RedditPost], list[HNPost], list[NewsArticle]]:
    """Fetch all source posts for the digest in one pass."""
    reddit_posts = list(
        RedditPost.objects.order_by("-posted_at").prefetch_related(
            Prefetch(
                "comments",
                queryset=RedditComment.objects.order_by("-score"),
            ),
        )[:REDDIT_POSTS_FOR_DIGEST]
    )
    hn_posts = list(
        HNPost.objects.order_by("-posted_at").prefetch_related(
            Prefetch(
                "comments",
                queryset=HNComment.objects.order_by("-posted_at"),
            ),
        )[:HN_POSTS_FOR_DIGEST]
    )
    news_articles = list(
        NewsArticle.objects.order_by("-published_at")[:NEWS_ARTICLES_FOR_DIGEST]
    )
    return reddit_posts, hn_posts, news_articles


def _build_prompt(
    reddit_posts: list[RedditPost],
    hn_posts: list[HNPost],
    news_articles: list[NewsArticle],
) -> str:
    sections = []

    if reddit_posts:
        lines = ["## Reddit Discussions"]
        for p in reddit_posts:
            lines.append(
                f"[r/{p.subreddit}] (score:{p.score}, comments:{p.num_comments}) {p.title}"
            )
            if p.body:
                lines.append(f"  {p.body[:REDDIT_POST_BODY_TRUNCATION]}")
            for c in p.comments.all()[:REDDIT_COMMENTS_PER_POST_FOR_DIGEST]:
                lines.append(
                    f"    > {c.author} (score:{c.score}): {c.body[:REDDIT_COMMENT_BODY_TRUNCATION]}"
                )
        sections.append("\n".join(lines))

    if hn_posts:
        lines = ["## Hacker News Discussions"]
        for p in hn_posts:
            lines.append(f"[HN] (score:{p.score}, comments:{p.num_comments}) {p.title}")
            for c in p.comments.all()[:HN_COMMENTS_PER_POST_FOR_DIGEST]:
                lines.append(f"    > {c.author}: {c.body[:HN_COMMENT_BODY_TRUNCATION]}")
        sections.append("\n".join(lines))

    if news_articles:
        lines = ["## News Articles"]
        for a in news_articles:
            date = a.published_at.strftime("%Y-%m-%d") if a.published_at else "unknown"
            lines.append(f"[{a.source}, {date}] {a.title}")
            if a.description:
                lines.append(f"  {a.description[:NEWS_ARTICLE_DESCRIPTION_TRUNCATION]}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _run_agent(prompt: str) -> MarketDigest:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            market_digest_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_market_digest() -> dict | None:
    """Return the cached market digest, regenerating if stale.

    Primary generation is handled by the hourly Celery beat task
    (analyst.tasks.generate_market_digest). This on-demand path acts as a
    fallback so the digest still refreshes if the beat worker is down or
    the cache expires between scheduled runs.
    """
    existing = cache.get(DIGEST_DATA_KEY)

    # If the digest is still fresh, return it immediately
    if existing and cache.get(DIGEST_FRESH_KEY):
        logger.debug("Market digest served from cache (fresh)")
        return existing

    # Digest is stale or missing — try to regenerate (on-demand fallback)
    if not cache.add(DIGEST_LOCK_KEY, True, DIGEST_LOCK_TTL):
        logger.debug("Market digest generation already in progress, serving stale")
        return existing

    reddit_posts, hn_posts, news_articles = _fetch_sources()
    prompt = _build_prompt(reddit_posts, hn_posts, news_articles)
    if not prompt:
        logger.warning("No data from any source, skipping digest")
        cache.delete(DIGEST_LOCK_KEY)
        return existing

    # Skip regeneration if sources haven't changed
    fingerprint = _source_fingerprint(reddit_posts, hn_posts, news_articles)
    if existing and existing.get("source_hash") == fingerprint:
        logger.debug("Digest sources unchanged, refreshing TTL")
        cache.set(DIGEST_FRESH_KEY, True, DIGEST_FRESHNESS_TTL)
        cache.delete(DIGEST_LOCK_KEY)
        return existing

    logger.info("Generating market digest from %d posts...", prompt.count("\n") + 1)

    try:
        digest = _run_agent(prompt)
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate market digest")
        cache.delete(DIGEST_LOCK_KEY)
        return existing

    data = digest.model_dump()
    data["source_hash"] = fingerprint
    data["generated_at"] = timezone.now().isoformat()
    logger.info("Market digest generated, freshness TTL %ds", DIGEST_FRESHNESS_TTL)
    cache.set(DIGEST_DATA_KEY, data, DIGEST_DATA_TTL)
    cache.set(DIGEST_FRESH_KEY, True, DIGEST_FRESHNESS_TTL)
    cache.delete(DIGEST_LOCK_KEY)
    return data
