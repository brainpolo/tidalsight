import time

from django.core.management.base import BaseCommand
from requests.exceptions import RequestException

from scraper.clients.yfinance_client import fetch_fundamentals
from scraper.models import Asset, Fundamental


class Command(BaseCommand):
    help = "Re-fetch fundamentals for all active assets to backfill new fields"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Seconds between API calls (default: 1.0)",
        )

    def handle(self, *args, **options):
        assets = Asset.objects.filter(is_active=True).order_by("ticker")
        total = assets.count()
        self.stdout.write(f"Backfilling fundamentals for {total} assets...")

        success = 0
        skipped = 0

        for i, asset in enumerate(assets, 1):
            self.stdout.write(f"  [{i}/{total}] {asset.ticker}...", ending=" ")

            try:
                data = fetch_fundamentals(asset.ticker)
            except (RequestException, ValueError) as e:
                self.stdout.write(self.style.ERROR(f"error: {e}"))
                skipped += 1
                continue

            if not data:
                self.stdout.write(self.style.WARNING("no data"))
                skipped += 1
                continue

            data.pop("name", None)
            data.pop("sector", None)
            data.pop("industry", None)

            Fundamental.objects.create(asset=asset, **data)
            success += 1
            self.stdout.write(self.style.SUCCESS("ok"))

            if i < total:
                time.sleep(options["delay"])

        self.stdout.write(
            self.style.SUCCESS(f"\nDone: {success} updated, {skipped} skipped")
        )
