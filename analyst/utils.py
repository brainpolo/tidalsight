from scraper.models import Asset


def asset_label(asset: Asset) -> str:
    """Standard label for prompts: 'AAPL (Apple Inc., Equity)'."""
    return f"{asset.ticker} ({asset.name}, {asset.get_asset_class_display()})"
