import logging

import httpx
from django.db import IntegrityError

from scraper.clients.hn_client import fetch_comments, fetch_top_stories
from scraper.constants import (
    EMBEDDING_MAX_COMMENTS,
    HN_DEFAULT_COMMENT_LIMIT,
    HN_MIN_SCORE,
    HN_TOP_STORIES_LIMIT,
)
from scraper.embeddings import gen_text_embedding
from scraper.managers.keyword_matcher import (
    build_asset_keyword_map,
    compile_keyword_pattern,
    match_assets,
)
from scraper.models import HNComment, HNPost

logger = logging.getLogger(__name__)


def _store_comments(post: HNPost) -> list[dict]:
    """Fetch and store top-level comments for a post. Returns the raw comment data."""
    try:
        comment_data_list = fetch_comments(post.hn_id, limit=HN_DEFAULT_COMMENT_LIMIT)
    except httpx.HTTPStatusError, httpx.RequestError:
        logger.exception("Failed to fetch comments for HN post %d", post.hn_id)
        return []

    for comment_data in comment_data_list:
        try:
            HNComment.objects.get_or_create(
                hn_id=comment_data["hn_id"],
                defaults={
                    "post": post,
                    "author": comment_data["author"],
                    "body": comment_data["text"],
                    "posted_at": comment_data["posted_at"],
                },
            )
        except IntegrityError:
            logger.exception("Failed to store HN comment %d", comment_data.get("hn_id"))

    return comment_data_list


def _generate_embedding(post: HNPost, comment_data_list: list[dict]) -> None:
    """Generate and store embedding for a post using its title and top comments."""
    # HN API returns comments in ranked order, so we take them as-is
    top_bodies = [c["text"] for c in comment_data_list[:EMBEDDING_MAX_COMMENTS]]
    try:
        post.embedding = gen_text_embedding(
            post.get_embedding_text(comment_bodies=top_bodies)
        )
        post.save(update_fields=["embedding"])
    except httpx.HTTPStatusError, httpx.RequestError, ValueError:
        logger.exception("Failed to generate embedding for HN post %d", post.hn_id)


def sync_hn_posts() -> int:
    """Fetch top HN stories, match to known assets, store with comments and embeddings."""
    keyword_map = build_asset_keyword_map()
    if not keyword_map:
        logger.warning("No assets in DB, skipping HN sync")
        return 0

    pattern = compile_keyword_pattern(keyword_map)
    stories = fetch_top_stories(limit=HN_TOP_STORIES_LIMIT)
    created_count = 0

    for story in stories:
        if story["score"] < HN_MIN_SCORE:
            continue

        matched_assets = match_assets(story["title"], keyword_map, pattern)
        if not matched_assets:
            continue

        post, created = HNPost.objects.update_or_create(
            hn_id=story["hn_id"],
            defaults={
                "title": story["title"],
                "url": story["url"],
                "author": story["author"],
                "score": story["score"],
                "num_comments": story["num_comments"],
                "posted_at": story["posted_at"],
            },
        )
        if created:
            post.assets.set(matched_assets)
            created_count += 1
            tickers = ", ".join(a.ticker for a in matched_assets)
            logger.info("HN post matched: '%s' → [%s]", story["title"][:60], tickers)

            comment_data_list = _store_comments(post)
            _generate_embedding(post, comment_data_list)

    logger.info(
        "HN sync complete: %d new posts (from %d stories scanned)",
        created_count,
        len(stories),
    )
    return created_count
