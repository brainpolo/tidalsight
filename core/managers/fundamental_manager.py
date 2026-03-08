from dataclasses import dataclass

from core.managers.valuation_manager import BROAD_MARKET_AVG_PE
from core.templatetags.formatting import abbreviate


@dataclass(frozen=True, slots=True)
class MetricMeta:
    label: str
    description: str
    icon: str = ""
    benchmark: str | None = None
    prefix: str = ""
    use_abbreviate: bool = False
    suffix: str = ""


METRIC_DESCRIPTIONS: dict[str, MetricMeta] = {
    "market_cap": MetricMeta(
        label="Market Cap",
        description="Total market value of all outstanding shares. Calculated as share price × total shares outstanding.",
        icon="landmark",
        prefix="$",
        use_abbreviate=True,
    ),
    "pe_ratio": MetricMeta(
        label="P/E Ratio",
        description=(
            "Price-to-Earnings ratio — how much investors pay per dollar of earnings. "
            "Higher P/E suggests growth expectations; lower P/E may indicate value."
        ),
        icon="gauge",
    ),
    "eps": MetricMeta(
        label="EPS",
        description=(
            "Earnings Per Share — net income divided by outstanding shares. "
            "Shows how much profit is attributable to each share."
        ),
        icon="coins",
        prefix="$",
    ),
    "dividend_yield": MetricMeta(
        label="Dividend Yield",
        description=(
            "Annual dividend payment as a percentage of the stock price. "
            "Higher yield means more income per dollar invested."
        ),
        icon="percent",
        benchmark="S&P 500 avg ~1.3%",
        suffix="%",
    ),
    "beta": MetricMeta(
        label="Beta",
        description=(
            "Measures volatility relative to the overall market. "
            "Beta of 1 = moves with the market. Above 1 = more volatile. Below 1 = less volatile."
        ),
        icon="activity",
        benchmark="Market = 1.00",
    ),
    "revenue": MetricMeta(
        label="Revenue",
        description="Total income generated from business operations before any expenses are deducted.",
        icon="banknote",
        prefix="$",
        use_abbreviate=True,
    ),
    "profit_margin": MetricMeta(
        label="Profit Margin",
        description=(
            "Percentage of revenue that becomes profit after all expenses. "
            "Higher margins indicate better cost efficiency."
        ),
        icon="scissors",
        benchmark="S&P 500 avg ~11%",
        suffix="%",
    ),
    "debt_to_equity": MetricMeta(
        label="Debt/Equity",
        description=(
            "Total liabilities divided by shareholder equity. "
            "Higher values mean more leverage. Below 1 is conservative; above 2 may signal risk."
        ),
        icon="scale",
        benchmark="Varies by sector",
    ),
    "free_cash_flow": MetricMeta(
        label="Free Cash Flow",
        description=(
            "Cash generated after capital expenditures. "
            "Shows how much real cash the business produces, unlike accounting earnings."
        ),
        icon="wallet",
        prefix="$",
        use_abbreviate=True,
    ),
    "return_on_equity": MetricMeta(
        label="ROE",
        description=(
            "Return on Equity — net income as a percentage of shareholder equity. "
            "Measures how efficiently a company turns invested capital into profit. Above 15% is generally strong."
        ),
        icon="target",
        benchmark="S&P 500 avg ~18%",
        suffix="%",
    ),
    "price_to_book": MetricMeta(
        label="P/B Ratio",
        description=(
            "Price-to-Book ratio — market price per share divided by book value per share. "
            "Below 1 may indicate undervaluation; above 3 suggests growth premium."
        ),
        icon="book-open",
        benchmark="S&P 500 avg ~4.5",
    ),
    "fifty_two_week_high": MetricMeta(
        label="52W High",
        description=(
            "Highest price reached in the past 52 weeks. "
            "Proximity to this level may indicate strong momentum or resistance."
        ),
        icon="chevron-up",
        prefix="$",
    ),
    "fifty_two_week_low": MetricMeta(
        label="52W Low",
        description=(
            "Lowest price reached in the past 52 weeks. "
            "Proximity to this level may indicate support or continued weakness."
        ),
        icon="chevron-down",
        prefix="$",
    ),
}

# Fields rendered as dedicated gauges instead of regular cards
GAUGE_FIELDS = {"pe_ratio", "fifty_two_week_high", "fifty_two_week_low"}

FUNDAMENTAL_FIELD_ORDER = [
    "market_cap",
    "eps",
    "dividend_yield",
    "beta",
    "revenue",
    "profit_margin",
    "debt_to_equity",
    "free_cash_flow",
    "return_on_equity",
    "price_to_book",
    "pe_ratio",
    "fifty_two_week_high",
    "fifty_two_week_low",
]


def build_fundamental_cards(fundamental, latest_price):
    """Build a list of fundamental metric dicts for template rendering."""
    if not fundamental:
        return []

    cards = []
    for field in FUNDAMENTAL_FIELD_ORDER:
        if field in GAUGE_FIELDS:
            continue

        raw = getattr(fundamental, field, None)
        if raw is None:
            continue

        meta = METRIC_DESCRIPTIONS.get(field)
        if not meta:
            continue

        if meta.use_abbreviate:
            display = abbreviate(raw)
        else:
            val = float(raw)
            display = (
                f"{meta.prefix}{val:,.2f}{meta.suffix}"
                if meta.prefix
                else f"{val:,.2f}{meta.suffix}"
            )

        cards.append(
            {
                "label": meta.label,
                "value": display,
                "description": meta.description,
                "benchmark": meta.benchmark,
                "icon": meta.icon,
                "field": field,
            }
        )

    range_gauge = _build_range_gauge(fundamental, latest_price)
    pe_gauge = _build_pe_gauge(fundamental)

    return {
        "cards": cards,
        "range_gauge": range_gauge,
        "pe_gauge": pe_gauge,
        "fetched_at": fundamental.fetched_at,
    }


def _build_range_gauge(fundamental, latest_price):
    if not (
        latest_price
        and fundamental.fifty_two_week_low
        and fundamental.fifty_two_week_high
    ):
        return None

    low = float(fundamental.fifty_two_week_low)
    high = float(fundamental.fifty_two_week_high)
    current = float(latest_price.close)

    pct = max(0, min(100, ((current - low) / (high - low)) * 100)) if high > low else 50

    return {
        "low": f"${low:,.2f}",
        "high": f"${high:,.2f}",
        "current": f"${current:,.2f}",
        "pct": round(pct, 1),
    }


def _build_pe_gauge(fundamental):
    if not fundamental.pe_ratio:
        return None

    pe = float(fundamental.pe_ratio)
    sector_avg = BROAD_MARKET_AVG_PE
    scale_max = max(pe * 1.2, sector_avg * 2.5, 50)
    pe_pct = max(0, min(100, (pe / scale_max) * 100))
    avg_pct = max(0, min(100, (sector_avg / scale_max) * 100))

    if pe > sector_avg * 1.3:
        label = "Expensive"
    elif pe < sector_avg * 0.7:
        label = "Cheap"
    else:
        label = "Fair"

    return {
        "value": f"{pe:.2f}",
        "sector_avg": sector_avg,
        "sector_avg_label": f"S&P {sector_avg}",
        "pe_pct": round(pe_pct, 1),
        "avg_pct": round(avg_pct, 1),
        "label": label,
    }
