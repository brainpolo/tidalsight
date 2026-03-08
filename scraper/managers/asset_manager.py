import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from requests.exceptions import RequestException

from scraper.clients.yfinance_client import fetch_asset_info, fetch_fundamentals, fetch_price_history
from scraper.constants import (
    DAILY_PRICE_INTERVAL,
    DAILY_PRICE_PERIOD,
    DAILY_PRICES_STALENESS_SECONDS,
    DEFAULT_PRICE_INTERVAL,
    DEFAULT_PRICE_PERIOD,
    FUNDAMENTALS_STALENESS_SECONDS,
    HOURLY_PRICES_STALENESS_SECONDS,
    SYNC_LOCK_TTL,
)
from scraper.models import Asset, Fundamental, PriceHistory

logger = logging.getLogger(__name__)


def get_or_create_asset(ticker: str) -> Asset:
    try:
        return Asset.objects.get(ticker=ticker)
    except Asset.DoesNotExist:
        pass

    lock_key = f"sync:asset_create:{ticker}"
    if not cache.add(lock_key, True, SYNC_LOCK_TTL):
        # Another request is already creating this asset — wait for it to appear
        logger.info("Asset creation for %s already in progress, retrying DB lookup", ticker)
        try:
            return Asset.objects.get(ticker=ticker)
        except Asset.DoesNotExist:
            raise ValueError(f"Asset creation for {ticker} in progress but not yet available")

    try:
        info = fetch_asset_info(ticker)
        if not info:
            raise ValueError(f"Could not find asset info for ticker: {ticker}")

        asset, created = Asset.objects.get_or_create(ticker=ticker, defaults=info)
        if created:
            logger.info("Created asset: %s", asset)
        return asset
    finally:
        cache.delete(lock_key)


def _sync_prices(asset: Asset, ticker: str, period: str, interval: str) -> int:
    staleness = DAILY_PRICES_STALENESS_SECONDS if interval == "1d" else HOURLY_PRICES_STALENESS_SECONDS

    latest = asset.prices.first()
    if latest and (timezone.now() - latest.timestamp).total_seconds() < staleness:
        logger.info("Prices for %s (%s) still fresh, skipping", ticker, interval)
        return 0

    lock_key = f"sync:prices:{ticker}:{interval}"
    if not cache.add(lock_key, True, SYNC_LOCK_TTL):
        logger.info("Price sync for %s (%s) already in progress, skipping", ticker, interval)
        return 0

    try:
        if interval == "1d":
            one_year_ago = timezone.now() - timedelta(days=400)
            has_old_data = asset.prices.filter(timestamp__lt=one_year_ago).exists()
            start = latest.timestamp if has_old_data else None
        else:
            start = latest.timestamp if latest else None

        try:
            rows = fetch_price_history(ticker, period=period, interval=interval, start=start)
        except (RequestException, ValueError):
            logger.exception("Failed to fetch price history for %s (%s)", ticker, interval)
            return 0

        if not rows:
            logger.warning("No price data returned for %s (%s)", ticker, interval)
            return 0

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

        created = PriceHistory.objects.bulk_create(objects, ignore_conflicts=True)

        logger.info("Synced %d %s prices for %s (%d new)", len(rows), interval, ticker, len(created))
        return len(created)
    finally:
        cache.delete(lock_key)


def sync_price_history(ticker: str, period: str = DEFAULT_PRICE_PERIOD, interval: str = DEFAULT_PRICE_INTERVAL) -> int:
    asset = get_or_create_asset(ticker)
    return _sync_prices(asset, ticker, period, interval)


def sync_all_prices(ticker: str) -> int:
    asset = get_or_create_asset(ticker)
    hourly = _sync_prices(asset, ticker, DEFAULT_PRICE_PERIOD, DEFAULT_PRICE_INTERVAL)
    daily = _sync_prices(asset, ticker, DAILY_PRICE_PERIOD, DAILY_PRICE_INTERVAL)
    return hourly + daily


def sync_fundamentals(ticker: str) -> Fundamental | None:
    asset = get_or_create_asset(ticker)

    latest = asset.fundamentals.first()
    if latest and (timezone.now() - latest.fetched_at).total_seconds() < FUNDAMENTALS_STALENESS_SECONDS:
        logger.info("Fundamentals for %s still fresh, skipping", ticker)
        return latest

    lock_key = f"sync:fundamentals:{ticker}"
    if not cache.add(lock_key, True, SYNC_LOCK_TTL):
        logger.info("Fundamentals sync for %s already in progress, skipping", ticker)
        return latest

    try:
        try:
            data = fetch_fundamentals(ticker)
        except (RequestException, ValueError):
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
