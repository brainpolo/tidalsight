import re
from urllib.parse import urlparse

from scraper.constants import ASSET_KEYWORD_MIN_LENGTH, ASSET_NAME_STOP_WORDS
from scraper.models import Asset


def build_asset_keyword_map() -> dict[str, list[Asset]]:
    """Build a mapping of lowercase keyword -> list of assets for title matching.

    Keywords are derived from:
    - Asset name words (excluding common suffixes like Inc, Corp, Ltd)
    - Asset ticker (3+ chars only to avoid false positives)
    - Website domain name (e.g. "google" from google.com)
    """
    assets = Asset.objects.filter(is_active=True).only(
        "id", "ticker", "name", "website"
    )
    keyword_map: dict[str, list[Asset]] = {}

    for asset in assets:
        keywords: set[str] = set()

        # Ticker (only 3+ chars to avoid matching "GC", "MS" etc. in random titles)
        if len(asset.ticker.rstrip("=-")) >= ASSET_KEYWORD_MIN_LENGTH:
            keywords.add(asset.ticker.lower())

        # Name words
        for word in asset.name.split():
            clean = re.sub(r"[.,()']", "", word).lower()
            if (
                len(clean) >= ASSET_KEYWORD_MIN_LENGTH
                and clean not in ASSET_NAME_STOP_WORDS
            ):
                keywords.add(clean)

        # Website domain (e.g. "google" from "https://www.google.com")
        if asset.website:
            host = urlparse(asset.website).hostname or ""
            domain = host.removeprefix("www.").split(".")[0].lower()
            if len(domain) >= ASSET_KEYWORD_MIN_LENGTH:
                keywords.add(domain)

        for kw in keywords:
            keyword_map.setdefault(kw, []).append(asset)

    return keyword_map


def compile_keyword_pattern(keyword_map: dict[str, list[Asset]]) -> re.Pattern:
    """Pre-compile a single regex that matches any keyword with word boundaries."""
    escaped = sorted((re.escape(kw) for kw in keyword_map), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def match_assets(
    text: str,
    keyword_map: dict[str, list[Asset]],
    pattern: re.Pattern,
) -> list[Asset]:
    """Match text against known asset keywords using a pre-compiled pattern."""
    matched: set[int] = set()
    matched_assets: list[Asset] = []

    for m in pattern.finditer(text):
        keyword = m.group(1).lower()
        for asset in keyword_map.get(keyword, []):
            if asset.pk not in matched:
                matched.add(asset.pk)
                matched_assets.append(asset)

    return matched_assets
