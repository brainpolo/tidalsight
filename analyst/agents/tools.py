from agents import function_tool
from pgvector.django import CosineDistance

from scraper.clients.brave_client import web_search as brave_web_search
from scraper.embeddings import gen_text_embedding
from scraper.managers.asset_manager import get_or_create_asset
from scraper.models import HNPost, NewsArticle, RedditPost


@function_tool
def validate_ticker(ticker: str) -> str:
    """Validate a ticker against Yahoo Finance. If valid, the asset is created in the
    database if it doesn't already exist. Call this before referencing any ticker."""
    ticker = ticker.upper().strip().lstrip("$")
    try:
        asset = get_or_create_asset(ticker)
        return (
            f"Valid: {asset.ticker} ({asset.name}, {asset.get_asset_class_display()})"
        )
    except ValueError, ConnectionError:
        return f"Invalid: {ticker} is not a recognized ticker. Do not reference it in the digest."


@function_tool
def search_web(query: str) -> str:
    """Search the web for real-time information. Use this to research competitors,
    industry peers, market data, or any factual question you need grounded answers for.
    Returns titles and descriptions of the top results."""
    try:
        results = brave_web_search(query, count=5)
    except Exception as e:
        return f"Search failed: {e}"
    if not results:
        return "No results found."
    lines = []
    for r in results:
        lines.append(f"- {r['title']}: {r['description']}")
    return "\n".join(lines)


@function_tool
def search_posts(query: str, ticker: str = "") -> str:
    """Search Reddit, Hacker News, and news articles stored in the database using
    semantic similarity. Use this to find community discussions, sentiment, and
    news coverage relevant to a topic. Optionally filter by ticker to scope results
    to a specific asset. Returns the top 5 most relevant results across all sources."""
    try:
        query_embedding = gen_text_embedding(query)
    except Exception as e:
        return f"Embedding generation failed: {e}"

    results = []

    for model, source, title_fn, detail_fn in [
        (
            RedditPost,
            "Reddit",
            lambda p: f"[r/{p.subreddit}] (score:{p.score}) {p.title}",
            lambda p: p.body[:200] if p.body else "",
        ),
        (
            HNPost,
            "HN",
            lambda p: f"[HN] (score:{p.score}) {p.title}",
            lambda p: "",
        ),
        (
            NewsArticle,
            "News",
            lambda a: f"[{a.source}] {a.title}",
            lambda a: a.description[:200] if a.description else "",
        ),
    ]:
        qs = model.objects.filter(embedding__isnull=False)
        if ticker:
            qs = qs.filter(assets__ticker=ticker.upper())
        matches = list(
            qs.annotate(distance=CosineDistance("embedding", query_embedding)).order_by(
                "distance"
            )[:5]
        )
        for m in matches:
            results.append((m.distance, source, title_fn(m), detail_fn(m)))

    results.sort(key=lambda x: x[0])
    results = results[:5]

    if not results:
        return "No matching posts found."

    lines = []
    for _distance, source, title, detail in results:
        line = f"- [{source}] {title}"
        if detail:
            line += f"\n    {detail}"
        lines.append(line)
    return "\n".join(lines)
