import asyncio
import hashlib
import logging

from agents import RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from django.core.cache import cache
from django.db.models import Prefetch
from django.utils import timezone

from analyst.agents.provider import get_model_provider
from analyst.agents.sentiment_agent import SentimentAnalysis, sentiment_agent
from analyst.app_behaviour import (
    MAX_AGENT_TURNS,
    REDDIT_COMMENT_BODY_TRUNCATION,
    REDDIT_POST_BODY_TRUNCATION,
    SENTIMENT_DATA_TTL,
    SENTIMENT_FRESHNESS_TTL,
    SENTIMENT_HN_COMMENTS_PER_POST,
    SENTIMENT_LOCK_TTL,
    SENTIMENT_MAX_POSTS,
    SENTIMENT_REDDIT_COMMENTS_PER_POST,
)
from analyst.grounding import agent_grounding
from scraper.models import (
    Asset,
    HNComment,
    HNPost,
    NewsArticle,
    RedditComment,
    RedditPost,
)

logger = logging.getLogger(__name__)


def _cache_keys(ticker: str) -> tuple[str, str, str]:
    return (
        f"sentiment:{ticker}:data",
        f"sentiment:{ticker}:fresh",
        f"sentiment:{ticker}:lock",
    )


def _get_community_posts(asset: Asset) -> tuple[list, list, list]:
    """Fetch reddit, HN, and news posts for the asset with prefetched comments."""
    reddit_posts = list(
        asset.reddit_posts.order_by("-posted_at").prefetch_related(
            Prefetch(
                "comments",
                queryset=RedditComment.objects.order_by("-score"),
            ),
        )
    )
    hn_posts = list(
        asset.hn_posts.order_by("-posted_at").prefetch_related(
            Prefetch(
                "comments",
                queryset=HNComment.objects.order_by("-posted_at"),
            ),
        )
    )
    news_articles = list(asset.news_articles.order_by("-published_at"))
    return reddit_posts, hn_posts, news_articles


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


def _build_prompt(
    asset: Asset,
    reddit_posts: list[RedditPost],
    hn_posts: list[HNPost],
    news_articles: list[NewsArticle],
) -> str:
    """Build a markdown prompt from community posts, merged by date descending."""
    entries = []

    for p in reddit_posts:
        ts = p.posted_at
        lines = [
            f"[Reddit r/{p.subreddit}] (score:{p.score}, comments:{p.num_comments}) {p.title}"
        ]
        if p.body:
            lines.append(f"  {p.body[:REDDIT_POST_BODY_TRUNCATION]}")
        for c in p.comments.all()[:SENTIMENT_REDDIT_COMMENTS_PER_POST]:
            lines.append(
                f"    > {c.author} (score:{c.score}): {c.body[:REDDIT_COMMENT_BODY_TRUNCATION]}"
            )
        entries.append((ts, "\n".join(lines)))

    for p in hn_posts:
        ts = p.posted_at
        lines = [f"[HN] (score:{p.score}, comments:{p.num_comments}) {p.title}"]
        for c in p.comments.all()[:SENTIMENT_HN_COMMENTS_PER_POST]:
            lines.append(f"    > {c.author}: {c.body[:150]}")
        entries.append((ts, "\n".join(lines)))

    for a in news_articles:
        ts = a.published_at or a.created_at
        lines = [f"[News, {a.source}] {a.title}"]
        if a.description:
            lines.append(f"  {a.description[:200]}")
        entries.append((ts, "\n".join(lines)))

    entries.sort(key=lambda x: x[0], reverse=True)
    entries = entries[:SENTIMENT_MAX_POSTS]

    header = f"# Community Posts for {asset.ticker} ({asset.name})\n\n"
    return header + "\n\n".join(text for _, text in entries)


def _run_agent(prompt: str) -> SentimentAnalysis:
    config = RunConfig(
        model_provider=get_model_provider(),
        tracing_disabled=True,
    )
    result = asyncio.run(
        Runner.run(
            sentiment_agent,
            input=prompt + agent_grounding(),
            run_config=config,
            max_turns=MAX_AGENT_TURNS,
        )
    )
    return result.final_output


def get_asset_sentiment(asset: Asset) -> dict | None:
    """Return cached sentiment analysis, regenerating if stale."""
    data_key, fresh_key, lock_key = _cache_keys(asset.ticker)

    existing = cache.get(data_key)

    if existing and cache.get(fresh_key):
        logger.debug("Sentiment for %s served from cache (fresh)", asset.ticker)
        return existing

    if not cache.add(lock_key, True, SENTIMENT_LOCK_TTL):
        logger.debug("Sentiment generation for %s already in progress", asset.ticker)
        return existing

    try:
        reddit_posts, hn_posts, news_articles = _get_community_posts(asset)
        total = len(reddit_posts) + len(hn_posts) + len(news_articles)

        if total < 5:
            logger.info("Not enough posts for %s sentiment (%d)", asset.ticker, total)
            cache.delete(lock_key)
            return None

        fingerprint = _source_fingerprint(reddit_posts, hn_posts, news_articles)

        if existing and existing.get("source_hash") == fingerprint:
            logger.debug(
                "Sentiment sources unchanged for %s, refreshing TTL", asset.ticker
            )
            cache.set(fresh_key, True, SENTIMENT_FRESHNESS_TTL)
            cache.delete(lock_key)
            return existing

        prompt = _build_prompt(asset, reddit_posts, hn_posts, news_articles)
        logger.info("Generating sentiment for %s from %d posts...", asset.ticker, total)

        sentiment = _run_agent(prompt)
        data = sentiment.model_dump()
        data["source_hash"] = fingerprint
        data["generated_at"] = timezone.now().isoformat()

        cache.set(data_key, data, SENTIMENT_DATA_TTL)
        cache.set(fresh_key, True, SENTIMENT_FRESHNESS_TTL)
        cache.delete(lock_key)
        return data
    except ConnectionError, RuntimeError, ValueError, TimeoutError, ModelBehaviorError:
        logger.exception("Failed to generate sentiment for %s", asset.ticker)
        cache.delete(lock_key)
        return existing
