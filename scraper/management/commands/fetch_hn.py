import httpx
from django.core.management.base import BaseCommand

from scraper.managers.hn_manager import sync_hn_posts


class Command(BaseCommand):
    help = "Fetch top Hacker News stories and match to known assets"

    def handle(self, *args, **options):
        self.stdout.write("Fetching top HN stories...")

        try:
            created = sync_hn_posts()
            self.stdout.write(self.style.SUCCESS(f"Done: {created} new posts matched to assets"))
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            self.stdout.write(self.style.ERROR(f"Failed: {e}"))
