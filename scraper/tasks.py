import logging
from datetime import timedelta
from typing import NamedTuple

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from scraper.constants import (
    REDDIT_DEFAULT_LIMIT,
    REDDIT_DEFAULT_SUBREDDITS,
)
from scraper.managers.asset_manager import (
    sync_all_prices,
    sync_full_prices,
    sync_fundamentals,
    sync_quick_prices,
)
from scraper.managers.brave_news_manager import sync_asset_news, sync_news
from scraper.managers.hn_manager import sync_hn_posts
from scraper.managers.reddit_manager import sync_reddit_posts
from scraper.models import Asset

# Top N assets by all-time views that always get price synced
_TOP_VIEWED_LIMIT = 100
# Weekly views window (7 days)
_WEEKLY_VIEWS_DAYS = 7

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


@shared_task(ignore_result=True)
def sync_new_asset_prices(asset_id: int):
    """Bootstrap prices for a brand-new asset (quick 1W then full backfill)."""
    asset = Asset.objects.get(id=asset_id)
    sync_quick_prices(asset, asset.ticker)
    sync_full_prices(asset, asset.ticker)
    logger.info("sync_new_asset_prices: done for %s", asset.ticker)


@shared_task(ignore_result=True)
def refresh_asset_prices(asset_id: int):
    """Refresh hourly + daily prices for an existing asset (staleness-guarded)."""
    asset = Asset.objects.get(id=asset_id)
    sync_all_prices(asset.ticker)
    logger.info("refresh_asset_prices: done for %s", asset.ticker)


@shared_task
def backfill_full_prices(asset_id: int, ticker: str):
    asset = Asset.objects.get(id=asset_id)
    sync_full_prices(asset, ticker)
    logger.info("backfill_full_prices: done for %s", ticker)


@shared_task
def fetch_asset_news(asset_id: int):
    asset = Asset.objects.get(id=asset_id)
    count = sync_asset_news(asset)
    logger.info("fetch_asset_news: %d new articles for %s", count, asset.ticker)
    return count


class _RelevantTickers(NamedTuple):
    crypto: list[str]
    traditional: list[str]


def _relevant_assets() -> _RelevantTickers:
    """Return tickers of assets worth syncing, partitioned by asset class.

    An asset qualifies if ANY of these hold:
    1. In at least one user's watchlist
    2. Has at least 1 view in the past 7 days
    3. Is in the top 100 most-viewed assets all-time
    """
    weekly_cutoff = timezone.now() - timedelta(days=_WEEKLY_VIEWS_DAYS)
    top_ids = (
        Asset.objects.filter(is_active=True)
        .order_by("-views")[:_TOP_VIEWED_LIMIT]
        .values("id")
    )

    assets = (
        Asset.objects.filter(
            Q(user_assets__in_watchlist=True)
            | Q(asset_views__viewed_at__gte=weekly_cutoff)
            | Q(pk__in=top_ids),
            is_active=True,
        )
        .values_list("ticker", "asset_class")
        .distinct()
    )

    crypto: list[str] = []
    traditional: list[str] = []
    for ticker, asset_class in assets:
        if asset_class == Asset.AssetClass.CRYPTO:
            crypto.append(ticker)
        else:
            traditional.append(ticker)
    return _RelevantTickers(crypto, traditional)


def _sync_tickers(tickers: list[str]) -> int:
    """Sync prices for a list of tickers, logging failures individually."""
    total = 0
    for ticker in tickers:
        try:
            total += sync_all_prices(ticker)
        except Exception:
            logger.exception("Failed to sync prices for %s", ticker)
    return total


@shared_task
def sync_crypto_prices():
    """Sync prices for relevant crypto assets (24/7 markets)."""
    tickers = _relevant_assets().crypto
    total = _sync_tickers(tickers)
    logger.info("sync_crypto_prices: %d new rows across %d assets", total, len(tickers))
    return total


@shared_task
def sync_traditional_prices():
    """Sync prices for relevant non-crypto assets (equity, commodity, etc.)."""
    tickers = _relevant_assets().traditional
    total = _sync_tickers(tickers)
    logger.info(
        "sync_traditional_prices: %d new rows across %d assets", total, len(tickers)
    )
    return total


@shared_task(ignore_result=True)
def fetch_fundamentals_for_asset(asset_id: int):
    """Sync fundamentals for a single asset (on-demand from views)."""
    asset = Asset.objects.get(id=asset_id)
    sync_fundamentals(asset.ticker)


@shared_task
def sync_watched_asset_fundamentals():
    """Sync fundamentals only for assets in at least one user's watchlist."""
    tickers = list(
        Asset.objects.filter(
            is_active=True,
            user_assets__in_watchlist=True,
        )
        .distinct()
        .values_list("ticker", flat=True)
    )
    updated = 0
    for ticker in tickers:
        try:
            if sync_fundamentals(ticker):
                updated += 1
        except Exception:
            logger.exception("Failed to sync fundamentals for %s", ticker)
    logger.info(
        "sync_watched_asset_fundamentals: %d/%d watched assets updated",
        updated,
        len(tickers),
    )
    return updated
