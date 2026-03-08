from agents import function_tool

from scraper.clients.brave_client import web_search as brave_web_search
from scraper.managers.asset_manager import get_or_create_asset


@function_tool
def validate_ticker(ticker: str) -> str:
    """Check whether a ticker symbol is real and tradeable. Call this for every ticker you
    plan to reference in the digest. If the ticker is invalid, do not mention it."""
    ticker = ticker.upper().strip().lstrip("$")
    try:
        asset = get_or_create_asset(ticker)
        return f"Valid: {asset.ticker} ({asset.name}, {asset.get_asset_class_display()})"
    except (ValueError, ConnectionError):
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
