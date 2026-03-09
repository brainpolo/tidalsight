import logging

from celery import shared_task

from analyst.managers.digest_manager import get_market_digest
from analyst.managers.peer_manager import sync_peers
from scraper.models import Asset

logger = logging.getLogger(__name__)


@shared_task
def discover_peers(asset_id: int) -> int:
    asset = Asset.objects.get(id=asset_id)
    peers = sync_peers(asset)
    return len(peers)


@shared_task
def generate_market_digest():
    digest = get_market_digest()
    if digest:
        logger.info("generate_market_digest: digest refreshed")
    else:
        logger.warning("generate_market_digest: no digest generated")
    return bool(digest)
