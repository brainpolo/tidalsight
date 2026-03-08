import logging

from celery import shared_task

from analyst.app_behaviour import SENTIMENT_MIN_POSTS
from analyst.managers.digest_manager import get_market_digest
from analyst.managers.peer_manager import sync_peers
from analyst.managers.sentiment_manager import get_asset_sentiment
from scraper.models import Asset

logger = logging.getLogger(__name__)


@shared_task
def discover_peers(asset_id: int) -> int:
    asset = Asset.objects.get(id=asset_id)
    peers = sync_peers(asset)
    return len(peers)


@shared_task
def analyze_asset_sentiment(asset_id: int) -> bool:
    asset = Asset.objects.get(id=asset_id)
    result = get_asset_sentiment(asset)
    if result:
        logger.info("analyze_asset_sentiment: sentiment refreshed for %s", asset.ticker)
    else:
        logger.warning(
            "analyze_asset_sentiment: no sentiment generated for %s", asset.ticker
        )
    return bool(result)


@shared_task
def refresh_all_sentiments():
    """Re-analyse sentiment for all active assets with enough community posts."""
    assets = Asset.objects.filter(is_active=True)
    refreshed = 0
    for asset in assets:
        total = (
            asset.reddit_posts.count()
            + asset.hn_posts.count()
            + asset.news_articles.count()
        )
        if total >= SENTIMENT_MIN_POSTS:
            analyze_asset_sentiment.delay(asset.id)
            refreshed += 1
    logger.info("refresh_all_sentiments: dispatched %d assets", refreshed)
    return refreshed


@shared_task
def generate_market_digest():
    digest = get_market_digest()
    if digest:
        logger.info("generate_market_digest: digest refreshed")
    else:
        logger.warning("generate_market_digest: no digest generated")
    return bool(digest)
