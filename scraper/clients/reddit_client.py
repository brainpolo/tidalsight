import logging
from datetime import UTC, datetime

import httpx

from scraper.constants import (
    REDDIT_DEFAULT_COMMENT_LIMIT,
    REDDIT_DEFAULT_LIMIT,
    REDDIT_USER_AGENT,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.reddit.com/r"


def fetch_posts(
    subreddit: str, sort: str = "hot", limit: int = REDDIT_DEFAULT_LIMIT
) -> list[dict]:
    url = f"{BASE_URL}/{subreddit}/{sort}.json"
    params = {"limit": limit}
    headers = {"User-Agent": REDDIT_USER_AGENT}

    response = httpx.get(
        url, params=params, headers=headers, timeout=15, follow_redirects=True
    )
    response.raise_for_status()

    try:
        children = response.json().get("data", {}).get("children", [])
    except ValueError:
        logger.warning("Malformed JSON from r/%s/%s", subreddit, sort)
        return []

    posts = []
    for child in children:
        data = child.get("data", {})

        if data.get("stickied"):
            continue

        posts.append(
            {
                "reddit_id": data.get("id", ""),
                "subreddit": data.get("subreddit", subreddit),
                "title": data.get("title", ""),
                "body": data.get("selftext", ""),
                "author": data.get("author", "[deleted]"),
                "score": data.get("score", 0),
                "upvote_ratio": data.get("upvote_ratio", 0.0),
                "num_comments": data.get("num_comments", 0),
                "url": f"https://www.reddit.com{data.get('permalink', '')}",
                "posted_at": datetime.fromtimestamp(data.get("created_utc", 0), tz=UTC),
            }
        )

    return posts


def fetch_comments(
    subreddit: str,
    post_id: str,
    limit: int = REDDIT_DEFAULT_COMMENT_LIMIT,
) -> list[dict]:
    url = f"{BASE_URL}/{subreddit}/comments/{post_id}.json"
    params = {"limit": limit, "sort": "top", "depth": 1}
    headers = {"User-Agent": REDDIT_USER_AGENT}

    response = httpx.get(
        url, params=params, headers=headers, timeout=15, follow_redirects=True
    )
    response.raise_for_status()

    data = response.json()
    if len(data) < 2:
        return []

    children = data[1].get("data", {}).get("children", [])

    comments = []
    for child in children:
        if child.get("kind") != "t1":
            continue

        cd = child.get("data", {})
        if cd.get("author") in ("[deleted]", "AutoModerator"):
            continue

        comments.append(
            {
                "reddit_id": cd.get("id", ""),
                "author": cd.get("author", "[deleted]"),
                "body": cd.get("body", ""),
                "score": cd.get("score", 0),
                "created_at": datetime.fromtimestamp(cd.get("created_utc", 0), tz=UTC),
            }
        )

    return comments
