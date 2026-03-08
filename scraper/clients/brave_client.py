import logging
from datetime import UTC, datetime

import httpx
from django.conf import settings

from scraper.constants import REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_NEWS_SEARCH_URL = "https://api.search.brave.com/res/v1/news/search"


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
    }


def web_search(
    query: str,
    *,
    count: int = 5,
    freshness: str | None = None,
    country: str = "us",
) -> list[dict]:
    """Search the web via Brave. Returns a list of {title, url, description} dicts.

    Used by analyst agents for grounding (competitor discovery, research, etc.).
    """
    params: dict = {
        "q": query,
        "count": count,
        "country": country,
    }
    if freshness:
        params["freshness"] = freshness

    r = httpx.get(
        BRAVE_WEB_SEARCH_URL,
        headers=_headers(),
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    data = r.json()

    results = []
    for item in data.get("web", {}).get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            }
        )

    logger.info("Brave web search for %r returned %d results", query, len(results))
    return results


def news_search(
    query: str,
    *,
    count: int = 20,
    freshness: str = "pw",
    country: str = "us",
) -> list[dict]:
    """Search news via Brave. Returns a list of article dicts.

    Used by the scraper pipeline to ingest financial news articles.
    """
    params: dict = {
        "q": query,
        "count": count,
        "freshness": freshness,
        "country": country,
    }

    r = httpx.get(
        BRAVE_NEWS_SEARCH_URL,
        headers=_headers(),
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    data = r.json()

    results = []
    for item in data.get("results", []):
        published_at = None
        meta_url = item.get("meta_url", {})
        # Brave provides page_age as ISO 8601 datetime, age is human-readable ("2 hours ago")
        for date_field in ("page_age", "age"):
            raw = item.get(date_field)
            if raw:
                try:
                    published_at = datetime.fromisoformat(raw)
                    if published_at.tzinfo is None:
                        published_at = published_at.replace(tzinfo=UTC)
                    break
                except ValueError, TypeError:
                    continue

        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "source": meta_url.get("hostname", "")
                if isinstance(meta_url, dict)
                else "",
                "published_at": published_at,
                "thumbnail": item.get("thumbnail", {}).get("src", "")
                if isinstance(item.get("thumbnail"), dict)
                else "",
            }
        )

    logger.info("Brave news search for %r returned %d results", query, len(results))
    return results
