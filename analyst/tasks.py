import logging

from celery import shared_task

from analyst.managers.description_manager import generate_description
from analyst.managers.digest_manager import get_market_digest
from analyst.managers.finance_manager import get_finance
from analyst.managers.overall_assessment_manager import get_overall_assessment
from analyst.managers.peer_manager import sync_peers
from analyst.managers.people_manager import get_people
from analyst.managers.personal_outlook_manager import get_personal_outlook
from analyst.managers.product_manager import get_product
from analyst.managers.risk_manager import get_risk
from analyst.managers.sentiment_manager import get_sentiment
from analyst.managers.valuation_manager import get_valuation
from core.models import UserAsset
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
        # Trigger personal outlook refresh for all users with watchlists
        user_ids = (
            UserAsset.objects.filter(in_watchlist=True)
            .values_list("user_id", flat=True)
            .distinct()
        )
        for uid in user_ids:
            generate_personal_outlook.delay(uid)
    else:
        logger.warning("Task generate_market_digest: no digest generated")
    return bool(digest)


@shared_task(ignore_result=True)
def generate_personal_outlook(user_id: int) -> None:
    logger.info("Task generate_personal_outlook started for user %s", user_id)
    get_personal_outlook(user_id)


# ── Report card section tasks ────────────────────────────────────────


@shared_task(ignore_result=True)
def analyse_sentiment(asset_id: int) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_sentiment started for %s", asset.ticker)
    get_sentiment(asset)


@shared_task(ignore_result=True)
def analyse_finance(asset_id: int) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_finance started for %s", asset.ticker)
    get_finance(asset)


@shared_task(ignore_result=True)
def analyse_risk(asset_id: int) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_risk started for %s", asset.ticker)
    get_risk(asset)


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
def analyse_product(
    asset_id: int,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_product started for %s (user %s)", asset.ticker, user_id)
    get_product(asset, user_id, user_note, price_target)


@shared_task(ignore_result=True)
def analyse_people(
    asset_id: int,
    user_id: int,
    user_note: str,
    price_target: float | None,
) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_people started for %s (user %s)", asset.ticker, user_id)
    get_people(asset, user_id, user_note, price_target)


@shared_task(ignore_result=True)
def analyse_overall(
    asset_id: int,
    user_id: int,
    sections: dict[str, dict],
) -> None:
    asset = Asset.objects.get(id=asset_id)
    logger.info("Task analyse_overall started for %s (user %s)", asset.ticker, user_id)
    get_overall_assessment(asset, user_id, sections)
