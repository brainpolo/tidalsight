def pct_change(current, previous):
    """Return percentage change from previous to current, or None if not computable."""
    if current is None or previous is None or previous == 0:
        return None
    return float((current - previous) / previous * 100)


def total_post_count() -> int:
    from scraper.models import HNPost, NewsArticle, RedditPost

    return (
        RedditPost.objects.count()
        + HNPost.objects.count()
        + NewsArticle.objects.count()
    )
