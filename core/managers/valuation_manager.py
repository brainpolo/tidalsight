# Graham Growth formula constants
GRAHAM_BASE_PE = 8.5
GRAHAM_GROWTH_MULTIPLIER = 2

# Gordon Growth Model (DDM) assumptions
DDM_GROWTH_RATE = 0.05  # 5% dividend growth
DDM_DISCOUNT_RATE = 0.10  # 10% required return
DDM_MIN_YIELD = 2  # minimum dividend yield % to apply DDM

# Annualized growth requires at least this many days of price history
MIN_GROWTH_DAYS = 30


def compute_valuations(asset, fundamental, latest_price):
    """Compute fair value estimates using well-known formulas.

    Returns a list of dicts: [{"name": ..., "value": Decimal, "delta_pct": float}, ...]
    Only includes valuations where we have sufficient data.
    """
    if not fundamental or not latest_price:
        return []

    current = float(latest_price.close)
    eps = float(fundamental.eps) if fundamental.eps else None
    dividend_yield = (
        float(fundamental.dividend_yield) if fundamental.dividend_yield else None
    )

    valuations = []

    # 1. Graham Growth: EPS x (8.5 + 2g) where g = annualized growth %
    if eps and eps > 0:
        growth = _annualized_growth(asset)
        if growth is not None:
            graham = eps * (GRAHAM_BASE_PE + GRAHAM_GROWTH_MULTIPLIER * growth)
            if graham > 0:
                valuations.append(
                    _build(
                        "Graham Growth",
                        graham,
                        current,
                        "Benjamin Graham's growth formula: EPS × (8.5 + 2g), where g is the annualized "
                        "historical growth rate. Estimates intrinsic value based on earnings and growth.",
                    )
                )

    # 2. P/E Fair Value: EPS x sector average P/E
    if eps and eps > 0:
        sector_pe = _sector_avg_pe(asset)
        pe_fair = eps * sector_pe
        if pe_fair > 0:
            valuations.append(
                _build(
                    "P/E Fair Value",
                    pe_fair,
                    current,
                    f"EPS × sector average P/E ratio ({sector_pe}). Shows what the stock would be "
                    "worth if it traded at the typical valuation multiple for its sector.",
                )
            )

    # 3. DDM (Gordon Growth): only for meaningful dividend stocks (yield > 2%)
    if dividend_yield and dividend_yield > DDM_MIN_YIELD and current > 0:
        annual_dividend = current * (dividend_yield / 100)
        if DDM_DISCOUNT_RATE > DDM_GROWTH_RATE:
            ddm = annual_dividend / (DDM_DISCOUNT_RATE - DDM_GROWTH_RATE)
            if ddm > 0:
                valuations.append(
                    _build(
                        "Dividend (DDM)",
                        ddm,
                        current,
                        "Gordon Growth Model: annual dividend ÷ (required return − dividend growth rate). "
                        f"Assumes {DDM_DISCOUNT_RATE:.0%} required return and {DDM_GROWTH_RATE:.0%} dividend growth. Best suited for stable dividend-paying stocks.",
                    )
                )

    # 4. Price/Sales: fair value if stock traded at sector avg P/S ratio
    market_cap = float(fundamental.market_cap) if fundamental.market_cap else None
    revenue = float(fundamental.revenue) if fundamental.revenue else None
    if market_cap and market_cap > 0 and revenue and revenue > 0 and current > 0:
        current_ps = market_cap / revenue
        sector_ps = _sector_avg_ps(asset)
        # Fair value = current price adjusted by how far P/S is from sector avg
        ps_fair = current * (sector_ps / current_ps)
        if ps_fair > 0:
            valuations.append(
                _build(
                    "Price/Sales",
                    ps_fair,
                    current,
                    f"Adjusts current price based on how the stock's Price/Sales ratio compares to the "
                    f"sector average ({sector_ps}x). Useful for valuing companies with low or negative earnings.",
                )
            )

    # 5. 52-Week Midpoint: simple mean of 52W high and low
    high = (
        float(fundamental.fifty_two_week_high)
        if fundamental.fifty_two_week_high
        else None
    )
    low = (
        float(fundamental.fifty_two_week_low)
        if fundamental.fifty_two_week_low
        else None
    )
    if high and low:
        midpoint = (high + low) / 2
        valuations.append(
            _build(
                "52W Midpoint",
                midpoint,
                current,
                "Simple average of the 52-week high and low. A rough gauge of where the stock "
                "sits within its annual trading range.",
            )
        )

    return valuations


def _build(name, fair_value, current, description=""):
    delta_pct = ((fair_value - current) / current) * 100
    return {
        "name": name,
        "value": round(fair_value, 2),
        "delta_pct": round(delta_pct, 1),
        "description": description,
    }


# Trailing P/E by S&P 500 sector — sourced from WorldPERatio.com, Mar 2026.
SECTOR_AVG_PE = {
    "technology": 36,
    "healthcare": 26,
    "financials": 18,
    "consumer_cyclical": 31,
    "consumer_defensive": 25,
    "industrials": 30,
    "energy": 21,
    "utilities": 21,
    "real_estate": 34,
    "communication_services": 18,
    "basic_materials": 23,
}
BROAD_MARKET_AVG_PE = 28

# P/S by S&P 500 sector — sourced from Damodaran/NYU Stern, Jan 2026.
SECTOR_AVG_PS = {
    "technology": 10,
    "healthcare": 5,
    "financials": 4,
    "consumer_cyclical": 2.5,
    "consumer_defensive": 2.5,
    "industrials": 2.5,
    "energy": 2,
    "utilities": 3,
    "real_estate": 5,
    "communication_services": 2.5,
    "basic_materials": 2.5,
}
BROAD_MARKET_AVG_PS = 3.3


def _sector_avg_pe(asset):
    """Return sector average P/E if asset class maps to a sector, else broad market avg."""
    asset_class = getattr(asset, "asset_class", "")
    if asset_class == "equity":
        # Default to technology for equities without a sector field
        return SECTOR_AVG_PE.get("technology", BROAD_MARKET_AVG_PE)
    return BROAD_MARKET_AVG_PE


def _sector_avg_ps(asset):
    """Return sector average P/S ratio."""
    asset_class = getattr(asset, "asset_class", "")
    if asset_class == "equity":
        return SECTOR_AVG_PS.get("technology", BROAD_MARKET_AVG_PS)
    return BROAD_MARKET_AVG_PS


def _annualized_growth(asset):
    """Compute annualized growth rate from earliest to latest price."""
    latest = asset.prices.first()
    earliest = asset.prices.order_by("timestamp").first()

    if not latest or not earliest or latest.pk == earliest.pk:
        return None

    start_price = float(earliest.close)
    end_price = float(latest.close)

    if start_price <= 0:
        return None

    days = (latest.timestamp - earliest.timestamp).days
    if days < MIN_GROWTH_DAYS:
        return None

    years = days / 365.25
    growth_rate = ((end_price / start_price) ** (1 / years) - 1) * 100
    return growth_rate
