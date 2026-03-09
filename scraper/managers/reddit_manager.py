import logging
import re

import httpx
from django.db import IntegrityError

from scraper.app_behaviour import REDDIT_MIN_SCORE
from scraper.clients.reddit_client import fetch_comments, fetch_posts
from scraper.constants import (
    EMBEDDING_MAX_COMMENTS,
    REDDIT_DEFAULT_LIMIT,
    REDDIT_DEFAULT_SUBREDDITS,
)
from scraper.embeddings import gen_text_embedding
from scraper.managers.asset_manager import (
    get_or_create_asset,
    sync_fundamentals,
    sync_price_history,
)
from scraper.models import Asset, RedditComment, RedditPost

logger = logging.getLogger(__name__)

CASHTAG_PATTERN = re.compile(r"(?<!\w)\$([A-Z]{1,5}(?:-[A-Z]{2,4})?)(?!\w)")


def _extract_tickers(text: str) -> set[str]:
    return set(CASHTAG_PATTERN.findall(text.upper()))


def _resolve_assets(title: str, body: str) -> list[Asset]:
    candidates = _extract_tickers(title) | _extract_tickers(body)
    if not candidates:
        return []

    assets = []
    for ticker in candidates:
        try:
            asset = get_or_create_asset(ticker)
            sync_price_history(ticker)
            sync_fundamentals(ticker)
            assets.append(asset)
            logger.info("Resolved ticker '%s' -> %s", ticker, asset)
        except ValueError, ConnectionError:
            logger.debug("Could not resolve ticker '%s', skipping", ticker)

    return assets


def _store_comments(post: RedditPost, subreddit: str, reddit_id: str) -> list[dict]:
    """Fetch and store comments for a post. Returns the raw comment data list."""
    comment_data_list = []
    try:
        comment_data_list = fetch_comments(subreddit, reddit_id)
    except httpx.HTTPStatusError, httpx.RequestError:
        logger.exception("Failed to fetch comments for post %s", reddit_id)
        return comment_data_list

    for comment_data in comment_data_list:
        try:
            RedditComment.objects.get_or_create(
                reddit_id=comment_data["reddit_id"],
                defaults={
                    "post": post,
                    "author": comment_data["author"],
                    "body": comment_data["body"],
                    "score": comment_data["score"],
                    "created_at": comment_data["created_at"],
                },
            )
        except IntegrityError:
            logger.exception(
                "Failed to store comment %s", comment_data.get("reddit_id")
            )

    return comment_data_list


def _generate_embedding(post: RedditPost, comment_data_list: list[dict]) -> None:
    """Generate and store embedding for a post using its content and top comments."""
    top_bodies = [
        c["body"]
        for c in sorted(comment_data_list, key=lambda c: c["score"], reverse=True)[
            :EMBEDDING_MAX_COMMENTS
        ]
    ]
    try:
        post.embedding = gen_text_embedding(
            post.get_embedding_text(comment_bodies=top_bodies)
        )
        post.save(update_fields=["embedding"])
    except httpx.HTTPStatusError, httpx.RequestError, ValueError:
        logger.exception("Failed to generate embedding for post %s", post.reddit_id)


def _link_assets(
    post: RedditPost, subreddit: str, comment_data_list: list[dict]
) -> None:
    """Resolve tickers from post and comment text, then link assets."""
    comment_bodies = " ".join(c["body"] for c in comment_data_list)
    assets = _resolve_assets(post.title, f"{post.body} {comment_bodies}")
    if assets:
        post.assets.set(assets)
        logger.info(
            "Linked r/%s post '%s' to %s",
            subreddit,
            post.title[:60],
            [a.ticker for a in assets],
        )


def sync_reddit_posts(
    subreddits: list[str] = REDDIT_DEFAULT_SUBREDDITS,
    sort: str = "hot",
    limit: int = REDDIT_DEFAULT_LIMIT,
) -> int:
    total_created = 0

    for subreddit in subreddits:
        try:
            posts = fetch_posts(subreddit, sort=sort, limit=limit)
        except httpx.HTTPStatusError, httpx.RequestError:
            logger.exception("Failed to fetch posts from r/%s", subreddit)
            continue

        for post_data in posts:
            if post_data.get("score", 0) < REDDIT_MIN_SCORE:
                continue

            reddit_id = post_data.pop("reddit_id")

            post, created = RedditPost.objects.update_or_create(
                reddit_id=reddit_id,
                defaults=post_data,
            )

            if created:
                total_created += 1
                comment_data_list = _store_comments(post, subreddit, reddit_id)
                _generate_embedding(post, comment_data_list)
                _link_assets(post, subreddit, comment_data_list)

        logger.info("Synced r/%s: %d posts fetched", subreddit, len(posts))

    logger.info("Reddit sync complete: %d new posts", total_created)
    return total_created
