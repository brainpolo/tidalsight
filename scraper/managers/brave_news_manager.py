import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
from django.core.cache import cache

from scraper.clients.brave_client import news_search
from scraper.constants import (
    BRAVE_NEWS_DEFAULT_COUNT,
    BRAVE_NEWS_DEFAULT_FRESHNESS,
    BRAVE_NEWS_DEFAULT_QUERY,
    BRAVE_NEWS_TICKER_STALENESS_SECONDS,
    SYNC_LOCK_TTL,
)
from scraper.embeddings import gen_text_embedding
from scraper.managers.keyword_matcher import build_asset_keyword_map, compile_keyword_pattern, match_assets
from scraper.models import Asset, NewsArticle

logger = logging.getLogger(__name__)


def _store_article(article_data: dict, matched_assets: list[Asset]) -> bool:
    """Store a single news article and link to assets. Returns True if newly created."""
    article, created = NewsArticle.objects.get_or_create(
        url=article_data["url"],
        defaults={
            "title": article_data["title"],
            "description": article_data.get("description", ""),
            "source": article_data.get("source", ""),
            "thumbnail": article_data.get("thumbnail", ""),
            "published_at": article_data.get("published_at"),
        },
    )

    if not created:
        return False

    if matched_assets:
        article.assets.set(matched_assets)

    try:
        article.embedding = gen_text_embedding(article.get_embedding_text())
        article.save(update_fields=["embedding"])
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError):
        logger.exception("Failed to generate embedding for article: %s", article.url)

    return True


def sync_news(
    query: str = BRAVE_NEWS_DEFAULT_QUERY,
    freshness: str = BRAVE_NEWS_DEFAULT_FRESHNESS,
    count: int = BRAVE_NEWS_DEFAULT_COUNT,
) -> int:
    """Fetch general financial news and link to assets via keyword matching."""
    keyword_map = build_asset_keyword_map()
    if not keyword_map:
        logger.warning("No assets in DB, skipping news sync")
        return 0

    pattern = compile_keyword_pattern(keyword_map)

    try:
        articles = news_search(query, count=count, freshness=freshness)
    except (httpx.HTTPStatusError, httpx.RequestError):
        logger.exception("Brave news search failed for query: %s", query)
        return 0

    created_count = 0
    for article_data in articles:
        text = f"{article_data['title']} {article_data.get('description', '')}"
        matched_assets = match_assets(text, keyword_map, pattern)

        if _store_article(article_data, matched_assets):
            created_count += 1
            if matched_assets:
                tickers = ", ".join(a.ticker for a in matched_assets)
                logger.info("News matched: '%s' → [%s]", article_data["title"][:60], tickers)

    logger.info("News sync complete: %d new articles (from %d fetched)", created_count, len(articles))
    return created_count


def sync_asset_news(asset: Asset, freshness: str = BRAVE_NEWS_DEFAULT_FRESHNESS) -> int:
    """Fetch news specifically about one asset and link directly.

    Uses a cache key to avoid re-fetching within BRAVE_NEWS_TICKER_STALENESS_SECONDS.
    """
    cache_key = f"news:asset:{asset.ticker}"
    if cache.get(cache_key):
        logger.info("News for %s still fresh, skipping", asset.ticker)
        return 0

    lock_key = f"sync:news:{asset.ticker}"
    if not cache.add(lock_key, True, SYNC_LOCK_TTL):
        logger.info("News sync for %s already in progress, skipping", asset.ticker)
        return 0

    try:
        query = f"{asset.ticker} {asset.name}"

        try:
            articles = news_search(query, freshness=freshness)
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.exception("Brave news search failed for asset: %s", asset.ticker)
            return 0

        created_count = 0
        for article_data in articles:
            if _store_article(article_data, [asset]):
                created_count += 1

        cache.set(cache_key, True, BRAVE_NEWS_TICKER_STALENESS_SECONDS)
        logger.info("Asset news sync for %s: %d new articles", asset.ticker, created_count)
        return created_count
    finally:
        cache.delete(lock_key)


_executor = ThreadPoolExecutor(max_workers=2)


def sync_asset_news_async(asset: Asset) -> None:
    """Fire-and-forget news sync for an asset in a background thread."""
    _executor.submit(sync_asset_news, asset)
