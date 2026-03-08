import logging
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests
import yfinance as yf

logger = logging.getLogger(__name__)


def _to_decimal(value, default=None):
    if value is None:
        return default
    try:
        floated = float(value)
        if math.isnan(floated) or math.isinf(floated):
            return default
        return Decimal(str(value))
    except InvalidOperation, ValueError, TypeError:
        return default


def fetch_price_history(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
    start: datetime | None = None,
) -> list[dict]:
    stock = yf.Ticker(ticker)
    if start:
        df = stock.history(start=start, interval=interval)
    else:
        df = stock.history(period=period, interval=interval)

    if df.empty:
        return []

    rows = []
    for ts, row in df.iterrows():
        rows.append(
            {
                "open": _to_decimal(row.get("Open")),
                "high": _to_decimal(row.get("High")),
                "low": _to_decimal(row.get("Low")),
                "close": _to_decimal(row.get("Close")),
                "volume": _to_decimal(row.get("Volume")),
                "timestamp": ts.to_pydatetime(),
            }
        )

    return rows


def fetch_fundamentals(ticker: str) -> dict | None:
    stock = yf.Ticker(ticker)
    info = stock.info

    if not info or info.get("regularMarketPrice") is None:
        return None

    return {
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": _to_decimal(info.get("marketCap")),
        "pe_ratio": _to_decimal(info.get("trailingPE")),
        "eps": _to_decimal(info.get("trailingEps")),
        "dividend_yield": _to_decimal(info.get("dividendYield")),
        "revenue": _to_decimal(info.get("totalRevenue")),
        "profit_margin": _to_decimal(info.get("profitMargins")),
        "beta": _to_decimal(info.get("beta")),
        "debt_to_equity": _to_decimal(info.get("debtToEquity")),
        "free_cash_flow": _to_decimal(info.get("freeCashflow")),
        "return_on_equity": _to_decimal(info.get("returnOnEquity")),
        "price_to_book": _to_decimal(info.get("priceToBook")),
        "fifty_two_week_high": _to_decimal(info.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _to_decimal(info.get("fiftyTwoWeekLow")),
    }


def fetch_asset_info(ticker: str) -> dict | None:
    stock = yf.Ticker(ticker)
    info = stock.info

    if not info or info.get("regularMarketPrice") is None:
        return None

    quote_type = info.get("quoteType", "").upper()
    asset_class_map = {
        "EQUITY": "equity",
        "CRYPTOCURRENCY": "crypto",
        "CURRENCY": "currency",
        "FUTURE": "commodity",
        "MUTUALFUND": "equity",
        "ETF": "equity",
    }

    return {
        "name": info.get("shortName") or info.get("longName") or ticker,
        "ticker": ticker,
        "asset_class": asset_class_map.get(quote_type, "equity"),
        "website": info.get("website") or "",
    }


YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"

YAHOO_QUOTE_TYPE_MAP = {
    "EQUITY": "equity",
    "CRYPTOCURRENCY": "crypto",
    "CURRENCY": "currency",
    "FUTURE": "commodity",
    "MUTUALFUND": "equity",
    "ETF": "equity",
}


def search_tickers(query: str, max_results: int = 6) -> list[dict]:
    """Search Yahoo Finance for tickers matching a natural-language query.

    Returns a list of dicts with keys: ticker, name, exchange, asset_class.
    """
    try:
        resp = requests.get(
            YAHOO_SEARCH_URL,
            params={
                "q": query,
                "quotesCount": max_results,
                "newsCount": 0,
                "listsCount": 0,
            },
            timeout=3,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        logger.warning("Yahoo Finance search failed for query: %s", query)
        return []

    results = []
    for quote in data.get("quotes", []):
        symbol = quote.get("symbol", "")
        if not symbol:
            continue
        quote_type = quote.get("quoteType", "").upper()
        results.append(
            {
                "ticker": symbol,
                "name": quote.get("shortname") or quote.get("longname") or symbol,
                "exchange": quote.get("exchange", ""),
                "asset_class": YAHOO_QUOTE_TYPE_MAP.get(quote_type, "equity"),
            }
        )

    return results
