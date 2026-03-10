import logging
from datetime import timedelta

from celery import shared_task
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
from scraper.models import Asset, AssetView

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


def _relevant_asset_ids() -> set[int]:
    """Return IDs of assets worth syncing prices for.

    An asset qualifies if ANY of these hold:
    1. In at least one user's watchlist
    2. Has at least 1 view in the past 7 days
    3. Is in the top 100 most-viewed assets all-time
    """
    weekly_cutoff = timezone.now() - timedelta(days=_WEEKLY_VIEWS_DAYS)

    # Condition 1: in a watchlist
    watched = set(
        Asset.objects.filter(
            is_active=True,
            user_assets__in_watchlist=True,
        ).values_list("id", flat=True)
    )

    # Condition 2: viewed in the last 7 days
    recently_viewed = set(
        AssetView.objects.filter(
            viewed_at__gte=weekly_cutoff,
            asset__is_active=True,
        )
        .values_list("asset_id", flat=True)
        .distinct()
    )

    # Condition 3: top 100 all-time views
    top_viewed = set(
        Asset.objects.filter(is_active=True)
        .order_by("-views")[:_TOP_VIEWED_LIMIT]
        .values_list("id", flat=True)
    )

    return watched | recently_viewed | top_viewed


@shared_task
def sync_crypto_prices():
    """Sync prices for relevant crypto assets (24/7 markets).

    Only syncs assets that are watched, recently viewed, or in the top 100
    most-viewed all-time — avoiding unnecessary API calls for idle assets.
    """
    relevant_ids = _relevant_asset_ids()
    tickers = list(
        Asset.objects.filter(
            id__in=relevant_ids,
            asset_class=Asset.AssetClass.CRYPTO,
        ).values_list("ticker", flat=True)
    )
    total = 0
    for ticker in tickers:
        try:
            total += sync_all_prices(ticker)
        except Exception:
            logger.exception("Failed to sync prices for %s", ticker)
    logger.info("sync_crypto_prices: %d new rows across %d assets", total, len(tickers))
    return total


@shared_task
def sync_traditional_prices():
    """Sync prices for relevant non-crypto assets (equity, commodity, etc.).

    Only syncs assets that are watched, recently viewed, or in the top 100
    most-viewed all-time — avoiding unnecessary API calls for idle assets.
    """
    relevant_ids = _relevant_asset_ids()
    tickers = list(
        Asset.objects.filter(
            id__in=relevant_ids,
        )
        .exclude(asset_class=Asset.AssetClass.CRYPTO)
        .values_list("ticker", flat=True)
    )
    total = 0
    for ticker in tickers:
        try:
            total += sync_all_prices(ticker)
        except Exception:
            logger.exception("Failed to sync prices for %s", ticker)
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
