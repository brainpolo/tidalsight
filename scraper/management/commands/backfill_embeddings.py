from django.core.management.base import BaseCommand

from scraper.embeddings import gen_text_embedding
from scraper.models import HNPost, NewsArticle, RedditPost


class Command(BaseCommand):
    help = "Backfill embeddings for Reddit and HN posts that don't have one yet"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of posts to process per batch (default: 100)",
        )

    def _backfill_model(self, queryset, label_fn, batch_size):
        total = queryset.count()
        if total == 0:
            self.stdout.write(f"  All {queryset.model.__name__} posts already have embeddings.")
            return 0, 0

        self.stdout.write(f"  Backfilling {total} {queryset.model.__name__} posts...")
        processed = 0
        failed = 0

        for post in queryset.iterator(chunk_size=batch_size):
            try:
                post.embedding = gen_text_embedding(post.get_embedding_text())
                post.save(update_fields=["embedding"])
                processed += 1
            except (ConnectionError, ValueError, RuntimeError) as e:
                failed += 1
                self.stderr.write(self.style.WARNING(f"  Failed for {label_fn(post)}: {e}"))

            if processed % batch_size == 0:
                self.stdout.write(f"    Progress: {processed}/{total}")

        return processed, failed

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        total_processed = 0
        total_failed = 0

        self.stdout.write("Backfilling Reddit posts...")
        p, f = self._backfill_model(
            RedditPost.objects.filter(embedding__isnull=True),
            lambda post: post.reddit_id,
            batch_size,
        )
        total_processed += p
        total_failed += f

        self.stdout.write("Backfilling HN posts...")
        p, f = self._backfill_model(
            HNPost.objects.filter(embedding__isnull=True),
            lambda post: f"hn:{post.hn_id}",
            batch_size,
        )
        total_processed += p
        total_failed += f

        self.stdout.write("Backfilling news articles...")
        p, f = self._backfill_model(
            NewsArticle.objects.filter(embedding__isnull=True),
            lambda article: article.url,
            batch_size,
        )
        total_processed += p
        total_failed += f

        self.stdout.write(
            self.style.SUCCESS(f"Done: {total_processed} embedded, {total_failed} failed.")
        )
