from django.core.management.base import BaseCommand, CommandError

from scraper.constants import (
    BRAVE_NEWS_DEFAULT_COUNT,
    BRAVE_NEWS_DEFAULT_FRESHNESS,
    BRAVE_NEWS_DEFAULT_QUERY,
)
from scraper.managers.brave_news_manager import sync_asset_news, sync_news
from scraper.models import Asset


class Command(BaseCommand):
    help = "Fetch news articles from Brave News Search and link to assets"

    def add_arguments(self, parser):
        parser.add_argument(
            "--query",
            type=str,
            default=BRAVE_NEWS_DEFAULT_QUERY,
            help=f"Search query (default: '{BRAVE_NEWS_DEFAULT_QUERY}')",
        )
        parser.add_argument(
            "--ticker",
            type=str,
            help="Fetch news for a specific asset ticker",
        )
        parser.add_argument(
            "--freshness",
            type=str,
            default=BRAVE_NEWS_DEFAULT_FRESHNESS,
            help=f"Brave freshness param: pd (day), pw (week), pm (month). Default: {BRAVE_NEWS_DEFAULT_FRESHNESS}",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=BRAVE_NEWS_DEFAULT_COUNT,
            help=f"Number of articles to fetch (default: {BRAVE_NEWS_DEFAULT_COUNT})",
        )

    def handle(self, *args, **options):
        ticker = options["ticker"]

        if ticker:
            ticker = ticker.upper()
            asset = Asset.objects.filter(ticker=ticker).first()
            if not asset:
                raise CommandError(f"Asset with ticker '{ticker}' not found")

            self.stdout.write(f"Fetching news for {asset.ticker} ({asset.name})...")
            count = sync_asset_news(asset, freshness=options["freshness"])
        else:
            self.stdout.write(
                f"Fetching general news: query='{options['query']}', freshness={options['freshness']}..."
            )
            count = sync_news(
                query=options["query"],
                freshness=options["freshness"],
                count=options["count"],
            )

        self.stdout.write(self.style.SUCCESS(f"Done: {count} new articles ingested."))
