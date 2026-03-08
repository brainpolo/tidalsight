import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.core.cache import cache
from django.db import close_old_connections
from django.utils import timezone
from requests.exceptions import RequestException

from scraper.clients.yfinance_client import (
    fetch_asset_info,
    fetch_fundamentals,
    fetch_price_history,
)
from scraper.constants import (
    DAILY_PRICE_INTERVAL,
    DAILY_PRICE_PERIOD,
    DAILY_PRICES_STALENESS_SECONDS,
    DEFAULT_PRICE_INTERVAL,
    DEFAULT_PRICE_PERIOD,
    FUNDAMENTALS_STALENESS_SECONDS,
    HOURLY_PRICES_STALENESS_SECONDS,
    QUICK_PRICE_PERIOD,
    SYNC_LOCK_TTL,
)
from scraper.models import Asset, Fundamental, PriceHistory

logger = logging.getLogger(__name__)


def _bulk_insert_prices(asset: Asset, rows: list[dict]) -> int:
    """Construct PriceHistory objects from raw rows and bulk-insert them.

    Returns the number of newly created rows. Duplicates (same asset +
    timestamp) are silently skipped via ignore_conflicts.
    """
    objects = [
        PriceHistory(
            asset=asset,
            timestamp=row["timestamp"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in rows
    ]
    return len(PriceHistory.objects.bulk_create(objects, ignore_conflicts=True))


def get_or_create_asset(ticker: str) -> Asset:
    try:
        return Asset.objects.get(ticker=ticker)
    except Asset.DoesNotExist:
        pass

    lock_key = f"sync:asset_create:{ticker}"
    if not cache.add(lock_key, True, SYNC_LOCK_TTL):
        # Another request is already creating this asset — wait for it to appear
        logger.info(
            "Asset creation for %s already in progress, retrying DB lookup", ticker
        )
        try:
            return Asset.objects.get(ticker=ticker)
        except Asset.DoesNotExist as err:
            raise ValueError(
                f"Asset creation for {ticker} in progress but not yet available"
            ) from err

    try:
        info = fetch_asset_info(ticker)
        if not info:
            raise ValueError(f"Could not find asset info for ticker: {ticker}")

        asset, created = Asset.objects.get_or_create(ticker=ticker, defaults=info)
        if created:
            logger.info("Created asset: %s", asset)
            try:
                from analyst.tasks import discover_peers

                discover_peers.delay(asset.id)
            except Exception:
                logger.warning("Failed to queue peer discovery for %s", ticker)
        return asset
    finally:
        cache.delete(lock_key)


def _sync_prices(asset: Asset, ticker: str, period: str, interval: str) -> int:
    staleness = (
        DAILY_PRICES_STALENESS_SECONDS
        if interval == "1d"
        else HOURLY_PRICES_STALENESS_SECONDS
    )

    latest = asset.prices.first()
    if latest and (timezone.now() - latest.timestamp).total_seconds() < staleness:
        logger.info("Prices for %s (%s) still fresh, skipping", ticker, interval)
        return 0

    lock_key = f"sync:prices:{ticker}:{interval}"
    if not cache.add(lock_key, True, SYNC_LOCK_TTL):
        logger.info(
            "Price sync for %s (%s) already in progress, skipping", ticker, interval
        )
        return 0

    try:
        if interval == "1d":
            one_year_ago = timezone.now() - timedelta(days=400)
            has_old_data = asset.prices.filter(timestamp__lt=one_year_ago).exists()
            start = latest.timestamp if has_old_data else None
        else:
            start = latest.timestamp if latest else None

        try:
            rows = fetch_price_history(
                ticker, period=period, interval=interval, start=start
            )
        except RequestException, ValueError:
            logger.exception(
                "Failed to fetch price history for %s (%s)", ticker, interval
            )
            return 0

        if not rows:
            logger.warning("No price data returned for %s (%s)", ticker, interval)
            return 0

        num_created = _bulk_insert_prices(asset, rows)
        logger.info(
            "Synced %d %s prices for %s (%d new)",
            len(rows),
            interval,
            ticker,
            num_created,
        )
        return num_created
    finally:
        cache.delete(lock_key)


def sync_price_history(
    ticker: str,
    period: str = DEFAULT_PRICE_PERIOD,
    interval: str = DEFAULT_PRICE_INTERVAL,
) -> int:
    asset = get_or_create_asset(ticker)
    return _sync_prices(asset, ticker, period, interval)


def sync_all_prices(ticker: str) -> int:
    asset = get_or_create_asset(ticker)
    hourly = _sync_prices(asset, ticker, DEFAULT_PRICE_PERIOD, DEFAULT_PRICE_INTERVAL)
    daily = _sync_prices(asset, ticker, DAILY_PRICE_PERIOD, DAILY_PRICE_INTERVAL)
    return hourly + daily


def sync_quick_prices(asset: Asset, ticker: str) -> int:
    """Synchronous 1-week hourly fetch for new assets with no price data.

    Called by asset_detail on first visit to a new ticker so the chart can
    render immediately (~1s) instead of waiting for the full history fetch.
    Pair with sync_full_prices_async() to backfill the remaining data.
    Cache-locked to prevent duplicate fetches from concurrent requests.
    """
    lock_key = f"sync:prices:{ticker}:quick"
    if not cache.add(lock_key, True, SYNC_LOCK_TTL):
        return 0

    try:
        try:
            rows = fetch_price_history(
                ticker, period=QUICK_PRICE_PERIOD, interval=DEFAULT_PRICE_INTERVAL
            )
        except RequestException, ValueError:
            logger.exception("Quick price sync failed for %s", ticker)
            return 0

        if not rows:
            logger.warning("No quick price data returned for %s", ticker)
            return 0

        num_created = _bulk_insert_prices(asset, rows)
        logger.info(
            "Quick-synced %d prices for %s (%d new)", len(rows), ticker, num_created
        )
        return num_created
    finally:
        cache.delete(lock_key)


_price_executor = ThreadPoolExecutor(max_workers=2)


def _sync_full_prices_thread(asset: Asset, ticker: str) -> None:
    """Background thread: fetch full hourly (1yr) + daily (all history) data.

    Hourly data covers chart ranges up to 1Y. Daily data (period="max")
    covers 5Y and ALL ranges. Bypasses _sync_prices for hourly because its
    staleness check would skip the fetch (quick sync data is fresh). Uses
    cache locks so if asset_header or another request is already syncing
    the same interval, this skips it. Overlapping rows from the quick sync
    are ignored via bulk_create's ignore_conflicts=True (unique constraint
    on asset + timestamp).
    """
    try:
        # Hourly: fetch full year (bypasses _sync_prices which would skip due to staleness)
        lock_key = f"sync:prices:{ticker}:{DEFAULT_PRICE_INTERVAL}"
        if cache.add(lock_key, True, SYNC_LOCK_TTL):
            try:
                rows = fetch_price_history(
                    ticker,
                    period=DEFAULT_PRICE_PERIOD,
                    interval=DEFAULT_PRICE_INTERVAL,
                )
                if rows:
                    num_created = _bulk_insert_prices(asset, rows)
                    logger.info(
                        "Background-synced %d hourly prices for %s (%d new)",
                        len(rows),
                        ticker,
                        num_created,
                    )
            except RequestException, ValueError:
                logger.exception("Background hourly sync failed for %s", ticker)
            finally:
                cache.delete(lock_key)

        # Daily: use existing _sync_prices (no staleness issue — no daily data exists)
        _sync_prices(asset, ticker, DAILY_PRICE_PERIOD, DAILY_PRICE_INTERVAL)
    finally:
        close_old_connections()


def sync_full_prices_async(asset: Asset, ticker: str) -> None:
    """Fire-and-forget full price backfill in a background thread.

    Intended to be called right after sync_quick_prices() so the user sees
    the 1W chart instantly while 1yr hourly + all daily history loads in
    the background. Once complete, all chart ranges (1M, 1Y, 5Y, ALL) become
    available. Cache locks prevent duplicate work if the background worker
    is already processing this ticker.
    """
    _price_executor.submit(_sync_full_prices_thread, asset, ticker)


def sync_fundamentals(ticker: str) -> Fundamental | None:
    asset = get_or_create_asset(ticker)

    latest = asset.fundamentals.first()
    if (
        latest
        and (timezone.now() - latest.fetched_at).total_seconds()
        < FUNDAMENTALS_STALENESS_SECONDS
    ):
        logger.info("Fundamentals for %s still fresh, skipping", ticker)
        return latest

    lock_key = f"sync:fundamentals:{ticker}"
    if not cache.add(lock_key, True, SYNC_LOCK_TTL):
        logger.info("Fundamentals sync for %s already in progress, skipping", ticker)
        return latest

    try:
        try:
            data = fetch_fundamentals(ticker)
        except RequestException, ValueError:
            logger.exception("Failed to fetch fundamentals for %s", ticker)
            return latest

        if not data:
            logger.warning("No fundamental data returned for %s", ticker)
            return latest

        data.pop("name", None)
        data.pop("sector", None)
        data.pop("industry", None)

        fundamental = Fundamental.objects.create(asset=asset, **data)
        logger.info("Saved fundamentals for %s", ticker)
        return fundamental
    finally:
        cache.delete(lock_key)
