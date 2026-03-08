from django.core.management.base import BaseCommand

from analyst.managers.peer_manager import sync_peers
from scraper.models import Asset


class Command(BaseCommand):
    help = "Discover and backfill peer/competitor assets for all active assets that don't have any"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ticker", type=str, help="Only backfill a specific ticker"
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-discover peers even if they already exist",
        )

    def handle(self, *args, **options):
        qs = Asset.objects.filter(is_active=True).order_by("ticker")

        if options["ticker"]:
            qs = qs.filter(ticker=options["ticker"].upper())

        if not options["force"]:
            qs = qs.filter(peers__isnull=True)

        assets = list(qs.distinct())
        total = len(assets)

        if not total:
            self.stdout.write("No assets need peer backfill.")
            return

        self.stdout.write(f"Backfilling peers for {total} asset(s)...")

        success = 0
        skipped = 0

        for i, asset in enumerate(assets, 1):
            self.stdout.write(f"  [{i}/{total}] {asset.ticker}...", ending=" ")

            if options["force"]:
                asset.peers.clear()

            try:
                peers = sync_peers(asset)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"error: {e}"))
                skipped += 1
                continue

            if peers:
                tickers = ", ".join(p.ticker for p in peers)
                self.stdout.write(self.style.SUCCESS(f"{len(peers)} peers ({tickers})"))
                success += 1
            else:
                self.stdout.write(self.style.WARNING("no peers found"))
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f"\nDone: {success} backfilled, {skipped} skipped")
        )
