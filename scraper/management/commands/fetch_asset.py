from django.core.management.base import BaseCommand
from requests.exceptions import RequestException

from scraper.managers.asset_manager import (
    get_or_create_asset,
    sync_all_prices,
    sync_fundamentals,
)


class Command(BaseCommand):
    help = "Fetch price history and fundamentals for one or more tickers"

    def add_arguments(self, parser):
        parser.add_argument(
            "tickers",
            nargs="+",
            type=str,
            help="Ticker symbols (e.g. AAPL BTC-USD GC=F)",
        )
        parser.add_argument(
            "--skip-prices", action="store_true", help="Skip fetching price history"
        )
        parser.add_argument(
            "--skip-fundamentals",
            action="store_true",
            help="Skip fetching fundamentals",
        )

    def handle(self, *args, **options):
        for ticker in options["tickers"]:
            ticker = ticker.upper()
            self.stdout.write(f"Processing {ticker}...")

            try:
                asset = get_or_create_asset(ticker)
                self.stdout.write(f"  Asset: {asset}")

                if not options["skip_prices"]:
                    created = sync_all_prices(ticker)
                    self.stdout.write(f"  Prices: {created} new rows (hourly + daily)")

                if not options["skip_fundamentals"]:
                    fundamental = sync_fundamentals(ticker)
                    if fundamental:
                        self.stdout.write("  Fundamentals: saved")
                    else:
                        self.stdout.write(self.style.WARNING("  Fundamentals: no data"))

                self.stdout.write(self.style.SUCCESS("  Done"))

            except (ValueError, RequestException) as e:
                self.stdout.write(self.style.ERROR(f"  Failed: {e}"))
