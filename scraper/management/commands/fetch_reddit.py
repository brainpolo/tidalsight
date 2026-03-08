import httpx
from django.core.management.base import BaseCommand

from scraper.constants import REDDIT_DEFAULT_LIMIT, REDDIT_DEFAULT_SUBREDDITS
from scraper.managers.reddit_manager import sync_reddit_posts


class Command(BaseCommand):
    help = "Fetch posts from Reddit subreddits and link to known assets"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subreddits",
            nargs="+",
            default=REDDIT_DEFAULT_SUBREDDITS,
            help=f"Subreddits to scrape (default: {', '.join(REDDIT_DEFAULT_SUBREDDITS)})",
        )
        parser.add_argument("--sort", default="hot", choices=["hot", "new", "top", "rising"], help="Sort order")
        parser.add_argument("--limit", type=int, default=REDDIT_DEFAULT_LIMIT, help=f"Posts per subreddit (default: {REDDIT_DEFAULT_LIMIT})")

    def handle(self, *args, **options):
        subreddits = options["subreddits"]
        sort = options["sort"]
        limit = options["limit"]

        self.stdout.write(f"Fetching {sort} posts from: {', '.join(subreddits)}")

        try:
            created = sync_reddit_posts(subreddits=subreddits, sort=sort, limit=limit)
            self.stdout.write(self.style.SUCCESS(f"Done: {created} new posts stored"))
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            self.stdout.write(self.style.ERROR(f"Failed: {e}"))
