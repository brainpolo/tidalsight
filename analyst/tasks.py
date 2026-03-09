import logging

from celery import shared_task

from analyst.managers.description_manager import generate_description
from analyst.managers.digest_manager import get_market_digest
from analyst.managers.external_risk_manager import get_external_risk
from analyst.managers.financial_health_manager import get_financial_health
from analyst.managers.leadership_manager import get_leadership
from analyst.managers.overall_assessment_manager import get_overall_assessment
from analyst.managers.peer_manager import sync_peers
from analyst.managers.product_flywheel_manager import get_product_flywheel
from analyst.managers.sentiment_manager import get_asset_sentiment
from analyst.managers.valuation_score_manager import get_valuation
from scraper.models import Asset

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def generate_asset_description(asset_id: int) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task generate_asset_description started for %s", asset.ticker)
    generate_description(asset)


@shared_task
def discover_peers(asset_id: int) -> int:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task discover_peers started for %s", asset.ticker)
    peers = sync_peers(asset)
    return len(peers)


@shared_task
def generate_market_digest():
    logger.info("Task generate_market_digest started")
    digest = get_market_digest()
    if digest:
        logger.info("Task generate_market_digest: digest refreshed")
    else:
        logger.warning("Task generate_market_digest: no digest generated")
    return bool(digest)


# ── Report card section tasks ────────────────────────────────────────


@shared_task(ignore_result=True)
def analyse_sentiment(asset_id: int) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_sentiment started for %s", asset.ticker)
    get_asset_sentiment(asset)


@shared_task(ignore_result=True)
def analyse_financial_health(asset_id: int) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_financial_health started for %s", asset.ticker)
    get_financial_health(asset)


@shared_task(ignore_result=True)
def analyse_external_risk(asset_id: int) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_external_risk started for %s", asset.ticker)
    get_external_risk(asset)


@shared_task(ignore_result=True)
def analyse_valuation(
    asset_id: int,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info(
        "Task analyse_valuation started for %s (user %s)", asset.ticker, user_id
    )
    get_valuation(asset, user_id, user_note, price_target)


@shared_task(ignore_result=True)
def analyse_product_flywheel(
    asset_id: int,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info(
        "Task analyse_product_flywheel started for %s (user %s)", asset.ticker, user_id
    )
    get_product_flywheel(asset, user_id, user_note, price_target)


@shared_task(ignore_result=True)
def analyse_leadership(
    asset_id: int,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info(
        "Task analyse_leadership started for %s (user %s)", asset.ticker, user_id
    )
    get_leadership(asset, user_id, user_note, price_target)


@shared_task(ignore_result=True)
def analyse_overall(
    asset_id: int,
    user_id: int,
    sections: dict[str, dict],
) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_overall started for %s (user %s)", asset.ticker, user_id)
    get_overall_assessment(asset, user_id, sections)
