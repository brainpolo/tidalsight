import logging
from datetime import UTC, datetime

import httpx

from scraper.constants import REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"


def fetch_top_story_ids(limit: int = 200) -> list[int]:
    r = httpx.get(f"{HN_API_BASE}/topstories.json", timeout=REQUEST_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()[:limit]


def fetch_item(item_id: int) -> dict | None:
    r = httpx.get(f"{HN_API_BASE}/item/{item_id}.json", timeout=REQUEST_TIMEOUT_SECONDS)
    if r.status_code != 200:
        return None
    return r.json()


def fetch_top_stories(limit: int = 200) -> list[dict]:
    """Fetch top stories from HN with basic details."""
    ids = fetch_top_story_ids(limit)
    stories = []

    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for item_id in ids:
            try:
                r = client.get(f"{HN_API_BASE}/item/{item_id}.json")
                if r.status_code != 200:
                    continue
                item = r.json()
                if (
                    not item
                    or item.get("type") != "story"
                    or item.get("dead")
                    or item.get("deleted")
                ):
                    continue
                stories.append(
                    {
                        "hn_id": item["id"],
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "author": item.get("by", ""),
                        "score": item.get("score", 0),
                        "num_comments": item.get("descendants", 0),
                        "posted_at": datetime.fromtimestamp(item["time"], tz=UTC),
                    }
                )
            except httpx.HTTPStatusError, httpx.RequestError, KeyError, ValueError:
                logger.debug("Failed to fetch HN item %d", item_id)
                continue

    logger.info("Fetched %d stories from HN (scanned %d IDs)", len(stories), len(ids))
    return stories


def fetch_comments(item_id: int, limit: int = 10) -> list[dict]:
    """Fetch top-level comments for a story."""
    story = fetch_item(item_id)
    if not story or not story.get("kids"):
        return []

    comments = []
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for kid_id in story["kids"][:limit]:
            try:
                r = client.get(f"{HN_API_BASE}/item/{kid_id}.json")
                if r.status_code != 200:
                    continue
                item = r.json()
                if (
                    not item
                    or item.get("type") != "comment"
                    or item.get("dead")
                    or item.get("deleted")
                ):
                    continue
                comments.append(
                    {
                        "hn_id": item["id"],
                        "author": item.get("by", ""),
                        "text": item.get("text", ""),
                        "posted_at": datetime.fromtimestamp(item["time"], tz=UTC),
                    }
                )
            except httpx.HTTPStatusError, httpx.RequestError, KeyError, ValueError:
                logger.debug("Failed to fetch HN comment %d", kid_id)
                continue

    return comments
