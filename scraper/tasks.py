import logging

from celery import shared_task

from scraper.constants import (
    REDDIT_DEFAULT_LIMIT,
    REDDIT_DEFAULT_SUBREDDITS,
)
from scraper.managers.brave_news_manager import sync_news
from scraper.managers.hn_manager import sync_hn_posts
from scraper.managers.reddit_manager import sync_reddit_posts

logger = logging.getLogger(__name__)


@shared_task
def fetch_hn():
    created = sync_hn_posts()
    logger.info("fetch_hn: %d new posts", created)
    return created


@shared_task
def fetch_reddit(subreddits=None, sort="hot", limit=REDDIT_DEFAULT_LIMIT):
    if subreddits is None:
        subreddits = REDDIT_DEFAULT_SUBREDDITS
    created = sync_reddit_posts(subreddits=subreddits, sort=sort, limit=limit)
    logger.info("fetch_reddit: %d new posts", created)
    return created


@shared_task
def fetch_news():
    count = sync_news()
    logger.info("fetch_news: %d new articles", count)
    return count
