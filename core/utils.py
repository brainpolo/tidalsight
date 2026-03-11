from collections import defaultdict

from django.db.models.functions import TruncDate

from core.app_behaviour import SPARKLINE_DATA_POINTS
from scraper.models import PriceHistory


def pct_change(current, previous):
    """Return percentage change from previous to current, or None if not computable."""
    if current is None or previous is None or previous == 0:
        return None
    return float((current - previous) / previous * 100)


async def fetch_sparkline_map(
    asset_ids: list[int],
    limit: int = SPARKLINE_DATA_POINTS,
) -> dict[int, list[float]]:
    """Batch-fetch sparkline close prices for multiple assets in one query.

    Returns {asset_id: [oldest_close, ..., newest_close]} with at most
    ``limit`` data points per asset.
    """
    if not asset_ids:
        return {}

    sparkline_map: dict[int, list[float]] = defaultdict(list)
    sparkline_qs = (
        PriceHistory.objects.filter(asset_id__in=asset_ids)
        .annotate(date=TruncDate("timestamp"))
        .order_by("asset_id", "-date", "-timestamp")
        .distinct("asset_id", "date")
        .values_list("asset_id", "close", "date")
    )
    async for asset_id, close, _date in sparkline_qs:
        if len(sparkline_map[asset_id]) < limit:
            sparkline_map[asset_id].append(float(close))

    for asset_id in sparkline_map:
        sparkline_map[asset_id].reverse()

    return dict(sparkline_map)


def total_post_count() -> int:
    from scraper.models import HNPost, NewsArticle, RedditPost

    return (
        RedditPost.objects.count()
        + HNPost.objects.count()
        + NewsArticle.objects.count()
    )
