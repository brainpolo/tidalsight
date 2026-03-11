"""Common grounding context appended to every agent prompt.

Appended (not prepended) so the task-specific data comes first — this
maximises KV-cache reuse when the same grounding block appears across
calls with different lead-in content.
"""

from django.utils import timezone

# Shared rubric for all 6 scoring agents (included in agent instructions)
SCORING_RUBRIC = (
    "## Scoring Scale (1.0 - 4.0)\n"
    "All scores use a strict 1-4 scale with up to one decimal place.\n\n"
    "- 1.0-1.4: Critical - severe deficiency, clear red flag\n"
    "- 1.5-1.9: Weak - material concerns, below average\n"
    "- 2.0-2.4: Below average - some issues, leans negative\n"
    "- 2.5-2.9: Average - passable but unremarkable\n"
    "- 3.0-3.4: Good - solid, above average\n"
    "- 3.5-3.9: Strong - meaningfully above peers\n"
    "- 4.0: Exceptional - top-decile across the market\n\n"
    "## Score Calibration (MANDATORY)\n"
    "Score like a precise calibrator. Your job is to place each asset exactly "
    "where the evidence demands, using the FULL 1.0-4.0 range. "
    "Do not hedge toward the middle.\n\n"
    "**Expected distribution across a broad portfolio:**\n"
    "- ~10-15% of assets score below 1.5 on any given dimension\n"
    "- ~15-20% score 1.5-2.0\n"
    "- ~15-20% score 2.0-2.5\n"
    "- ~15-20% score 2.5-3.0\n"
    "- ~15-20% score 3.0-3.5\n"
    "- ~10-15% score above 3.5\n\n"
    "A score between 2.0 and 3.0 should only be given when the evidence is "
    "genuinely mixed or mediocre. Most assets have clear strengths and clear "
    "weaknesses — place the score where the evidence points, even if that "
    "means 1.2 or 3.8.\n\n"
    "**Low scores are accurate, not punitive.** When evidence shows clear "
    "weakness, scoring above 2.0 is dishonest. Do not inflate scores out of "
    "caution or politeness. A company losing money with rising debt belongs "
    "below 1.5 on finance. A token with declining users and no developer "
    "activity belongs below 1.5 on product. An asset under active government "
    "investigation belongs below 1.5 on risk.\n\n"
    "**High scores are earned, not reckless.** When evidence shows clear "
    "strength, scoring below 3.0 is equally dishonest. Do not suppress scores "
    "out of false modesty. A company with 40% margins, zero debt, and 20% "
    "growth belongs above 3.5 on finance. A protocol dominating its category "
    "with 60% market share belongs above 3.5 on product.\n\n"
    "Name recognition, market cap, popularity, and past performance are "
    "IRRELEVANT. A trillion-dollar asset can score 1.0 if the evidence "
    "warrants it. A micro-cap can score 4.0 if the evidence warrants it. "
    "No asset is above a low score or below a high score.\n"
)


# Deterministic label mapping per section — computed from score, never LLM-generated.
# Each list is (upper_bound_exclusive, label).
SECTION_LABELS: dict[str, list[tuple[float, str]]] = {
    "finance": [
        (1.5, "Critical"),
        (2.0, "Weak"),
        (3.0, "Fair"),
        (3.5, "Strong"),
        (999, "Excellent"),
    ],
    "sentiment": [
        (1.5, "Very Bearish"),
        (2.0, "Bearish"),
        (3.0, "Neutral"),
        (3.5, "Bullish"),
        (999, "Very Bullish"),
    ],
    "risk": [
        (1.5, "Critical"),
        (2.0, "Elevated"),
        (3.0, "Moderate"),
        (3.5, "Low"),
        (999, "Minimal"),
    ],
    "valuation": [
        (1.5, "Deeply Overvalued"),
        (2.0, "Overvalued"),
        (3.0, "Fair"),
        (3.5, "Undervalued"),
        (999, "Deeply Undervalued"),
    ],
    "product": [
        (1.5, "Absent"),
        (2.0, "Weak"),
        (3.0, "Developing"),
        (3.5, "Strong"),
        (999, "Exceptional"),
    ],
    "people": [
        (1.5, "Weak"),
        (2.0, "Concerning"),
        (3.0, "Capable"),
        (3.5, "Strong"),
        (999, "Exceptional"),
    ],
}


# Per-section, per-asset-class calibration anchors.
# Each entry is (low_anchor_text, high_anchor_text).
_CALIBRATION: dict[str, dict[str, tuple[str, str]]] = {
    "sentiment": {
        "equity": (
            "- Fraud or accounting scandal dominates discussion, mass analyst "
            "downgrades, class-action lawsuits filed, CEO resignation under "
            "pressure, earnings miss combined with guidance cut and insider selling",
            "- Blowout earnings with raised guidance and multiple analyst "
            "upgrades, transformative acquisition praised universally, product "
            "launch with viral adoption, broad 'generational buy' consensus "
            "with concrete catalysts cited",
        ),
        "crypto": (
            "- 'Rug pull' or 'exit scam' narrative, exchange delisting "
            "announcements, founder arrested or investigated, protocol exploit "
            "with fund losses, community exodus and mass wallet withdrawals",
            "- Spot ETF approval euphoria, major institutional adoption "
            "announcement, successful protocol upgrade celebrated by developers, "
            "regulatory clarity positive surprise",
        ),
        "commodity": (
            "- Demand destruction narrative dominant with no dissenters, "
            "massive inventory builds reported, substitute technology "
            "breakthrough consensus, major buyer cancelling contracts",
            "- Supply crisis with physical shortages reported, geopolitical "
            "disruption to a major producer, 'supercycle' narrative backed by "
            "hard inventory data, weather disaster destroying supply",
        ),
        "currency": (
            "- Hyperinflation panic, sovereign default fear, capital flight "
            "discussions, emergency central bank intervention, sanctions "
            "cutting off international payment systems",
            "- Surprise hawkish central bank pivot, safe-haven surge during "
            "global crisis, major trade deal boosting demand, reserve "
            "accumulation by multiple central banks",
        ),
    },
    "finance": {
        "equity": (
            "- Negative net income for 3+ consecutive years with no improving trend\n"
            "- Debt/Equity ratio above 3x with declining revenue\n"
            "- Negative free cash flow AND current ratio below 0.5\n"
            "- Profit margins deeply negative (-20% or worse) in a mature business\n"
            "- Combination of high leverage, negative earnings, and cash burn",
            "- Profit margins above 30% with stable or expanding trend\n"
            "- Debt/Equity below 0.3 with strong free cash flow generation\n"
            "- ROE above 25% sustained over multiple periods\n"
            "- Revenue growing above 15% YoY with positive and expanding margins\n"
            "- Combination of high profitability, low leverage, and strong cash generation",
        ),
    },
    "risk": {
        "equity": (
            "- Active government investigation or existential lawsuit, market "
            "share collapsing (>20% loss in 2 years), antitrust breakup "
            "proceedings, supply chain concentrated in a single sanctioned country",
            "- Regulated monopoly or duopoly with government-backed position, "
            "no material litigation or regulatory threats, diversified global "
            "revenue with no single-country dependency above 30%",
        ),
        "crypto": (
            "- SEC or equivalent enforcement action pending, exchange bans in "
            "major markets, history of protocol exploits with fund losses, "
            "validator/miner concentration above 50%, stablecoin depeg "
            "contagion risk",
            "- Full regulatory clarity in major jurisdictions, spot ETF "
            "approved, institutional custody infrastructure mature, "
            "battle-tested protocol with no exploit history over 5+ years",
        ),
        "commodity": (
            "- Viable substitute technology reaching price parity, cartel "
            "collapse destabilising supply, ESG regulation banning primary "
            "use case, single-country supply concentration above 60% under "
            "geopolitical threat",
            "- Irreplaceable industrial input with no viable substitute, "
            "diversified global supply, stable and predictable demand, low "
            "geopolitical exposure",
        ),
        "currency": (
            "- Active sovereign debt crisis, hyperinflation above 50% "
            "annualised, international sanctions regime in effect, central "
            "bank credibility destroyed by policy reversals",
            "- Reserve currency status, AAA-rated sovereign, deep liquid "
            "markets, independent central bank with strong credibility",
        ),
    },
    "valuation": {
        "equity": (
            "- Trading above all fair value models by 50%+, P/E above 80 "
            "with decelerating growth, RSI above 80, multiple expansion "
            "already priced in with no catalyst remaining",
            "- Trading below all fair value models by 30%+, P/E below 8 "
            "with stable or growing earnings, RSI below 25, market pricing "
            "in a worst case that is unlikely",
        ),
        "crypto": (
            "- Price far above realised value (MVRV well above 3), NVT at "
            "historical extremes, euphoric retail inflows with no fundamental "
            "change, trading multiples of previous cycle highs",
            "- Price below realised value (MVRV below 1), NVT at historical "
            "lows, capitulation volume with long-term holders accumulating, "
            "fundamentals improving while price declines",
        ),
        "commodity": (
            "- In steep contango, price more than 2 standard deviations above "
            "marginal production cost, inventory builds accelerating, demand "
            "forecasts being revised downward",
            "- In steep backwardation, price at or below marginal production "
            "cost, inventory draws accelerating, supply disruptions unresolved",
        ),
        "currency": (
            "- PPP more than 30% overvalued, carry trade fully priced and "
            "crowded, real rates deeply negative relative to peers, current "
            "account deficit widening",
            "- PPP more than 30% undervalued, real rates attractive relative "
            "to peers, current account surplus, central bank credible and "
            "tightening",
        ),
    },
    "product": {
        "equity": (
            "- Single product with declining market share, no switching costs, "
            "open-source or low-cost alternatives gaining traction, no visible "
            "flywheel or cross-sell dynamics, R&D spend producing no new products",
            "- Multi-product platform with proven self-reinforcing flywheel, "
            "above 40% market share in core segment, high and rising switching "
            "costs, thriving developer or partner ecosystem, strong R&D pipeline",
        ),
        "crypto": (
            "- No real utility beyond speculation, declining active addresses "
            "and TVL, near-zero developer commits, no DeFi ecosystem, "
            "technically inferior to competitors with no differentiator",
            "- Dominant L1 or category leader with thriving ecosystem, above "
            "40% TVL or market share in its category, strong and growing "
            "developer activity, mature institutional infrastructure, "
            "battle-tested technology",
        ),
        "commodity": (
            "- Facing viable synthetic or alternative substitution at price "
            "parity, demand elasticity above 1, declining industrial relevance "
            "as technology shifts to alternatives",
            "- Irreplaceable in critical industrial applications, highly "
            "inelastic demand, no viable substitutes at any price, essential "
            "input for growing industries",
        ),
        "currency": (
            "- Declining share of global trade settlement, digital alternatives "
            "gaining adoption, capital controls limiting international use, "
            "shrinking role in reserve portfolios",
            "- Primary global reserve currency, dominant in international trade "
            "settlement, deepest and most liquid markets, trusted store of "
            "value during crises",
        ),
    },
    "people": {
        "equity": (
            "- 3+ C-suite departures within 18 months\n"
            "- Glassdoor rating below 3.0 or declining by more than 1 point\n"
            "- Mass layoffs combined with hiring freeze and executive turnover\n"
            "- Founder departed acrimoniously or was removed by the board\n"
            "- Significant insider selling (executives dumping stock)\n"
            "- Active governance scandal, fraud investigation, or activist "
            "campaign targeting leadership",
            "- Founder-CEO with 15+ year track record of execution\n"
            "- Glassdoor above 4.3 with stable or rising trend\n"
            "- Top-tier talent actively joining from leading competitors\n"
            "- Strong succession planning with proven internal pipeline\n"
            "- Consistent insider buying by executives\n"
            "- Industry-leading employer brand attracting best-in-class candidates",
        ),
    },
}

_POLARITY_NOTES: dict[str, str] = {
    "risk": "remember: HIGHER = safer",
    "valuation": "remember: HIGHER = more undervalued",
}


def calibration_anchors(section: str, asset_class: str) -> str:
    """Return calibration anchor text for a specific section and asset class."""
    anchors = _CALIBRATION.get(section, {})
    entry = anchors.get(asset_class)
    if not entry:
        return ""
    low, high = entry
    polarity = _POLARITY_NOTES.get(section)
    header = "## Calibration Anchors"
    if polarity:
        header += f" ({polarity})"
    return (
        f"\n\n{header}\n"
        f"Scores of 1.0-1.4 are warranted when:\n{low}\n\n"
        f"Scores of 3.5-4.0 are warranted when:\n{high}\n"
    )


def compute_label(section: str, score: float) -> str:
    """Map a section score to its deterministic label."""
    for threshold, label in SECTION_LABELS[section]:
        if score < threshold:
            return label
    return SECTION_LABELS[section][-1][1]


def agent_grounding() -> str:
    today = timezone.now().date()
    return (
        "\n\n---\n"
        "## Grounding Context\n"
        f"- Current date: {today.strftime('%B %d, %Y')}\n"
        "\n"
        "## Response Standards\n"
        "- Be direct and specific. No disclaimers, no hedging, no filler.\n"
        "- Reference concrete numbers, names, and facts — not vague generalities.\n"
        "- Write in present tense unless referring to historical events.\n"
        "- Never say 'As of [year]' — state facts directly.\n"
        "- Professional tone: institutional research quality, not retail/blog style.\n"
        "- If you lack information, say so briefly rather than fabricating.\n"
    )
