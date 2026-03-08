import logging

from celery import shared_task

from scraper.constants import (
    REDDIT_DEFAULT_LIMIT,
    REDDIT_DEFAULT_SUBREDDITS,
)
from scraper.managers.asset_manager import sync_all_prices, sync_fundamentals
from scraper.managers.brave_news_manager import sync_news
from scraper.managers.hn_manager import sync_hn_posts
from scraper.managers.reddit_manager import sync_reddit_posts
from scraper.models import Asset

logger = logging.getLogger(__name__)


@shared_task
def fetch_hn():
    created = sync_hn_posts()
    logger.info("fetch_hn: %d new posts", created)
    return created


@shared_task
def fetch_reddit(subreddits=None, sort="hot", limit=REDDIT_DEFAULT_LIMIT):
    if subreddits is None:
        subreddits = REDDIT_DEFAULT_SUBREDDITS
    created = sync_reddit_posts(subreddits=subreddits, sort=sort, limit=limit)
    logger.info("fetch_reddit: %d new posts", created)
    return created


@shared_task
def fetch_news():
    count = sync_news()
    logger.info("fetch_news: %d new articles", count)
    return count


@shared_task
def sync_all_asset_prices():
    tickers = list(
        Asset.objects.filter(is_active=True).values_list("ticker", flat=True)
    )
    total = 0
    for ticker in tickers:
        try:
            total += sync_all_prices(ticker)
        except Exception:
            logger.exception("Failed to sync prices for %s", ticker)
    logger.info(
        "sync_all_asset_prices: %d new rows across %d assets", total, len(tickers)
    )
    return total


@shared_task
def sync_all_asset_fundamentals():
    tickers = list(
        Asset.objects.filter(is_active=True).values_list("ticker", flat=True)
    )
    updated = 0
    for ticker in tickers:
        try:
            if sync_fundamentals(ticker):
                updated += 1
        except Exception:
            logger.exception("Failed to sync fundamentals for %s", ticker)
    logger.info("sync_all_asset_fundamentals: %d assets updated", updated)
    return updated
