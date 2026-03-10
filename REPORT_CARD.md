# Report Card

Asset-level scoring system that produces a holistic buy/sell/hold assessment across up to 6 dimensions, each scored out of 5, culminating in an overall verdict with a 12-month price target. Equities are assessed on all 6 dimensions; crypto, commodities, and currencies use 4 (Financial Health and Leadership are equity-only). Scores are scaled to a consistent 0–30 range regardless of section count.

## Philosophy — Herzberg's Two-Factor Theory

The report card is structured around [Herzberg's Two-Factor Theory](https://en.wikipedia.org/wiki/Two-factor_theory), separating analysis into **Hygiene Factors** (baseline requirements that prevent failure) and **Motivators** (growth drivers that create upside).

**Hygiene Factors** — things that must be sound or the investment fails regardless of upside:

| # | Section | What it answers | Asset classes |
|---|---------|-----------------|---------------|
| 1 | **Financial Health** | Is the balance sheet solid? Revenue growing? Margins healthy? | Equities only |
| 2 | **Sentiment** | What does the market think? Is crowd sentiment aligned or divergent? | All |
| 3 | **External Risk** | What macro, regulatory, or geopolitical threats exist? | All |

**Motivators** — things that create differentiated upside:

| # | Section | What it answers | Asset classes |
|---|---------|-----------------|---------------|
| 4 | **Valuation** | Is the asset cheap or expensive relative to intrinsic value? | All |
| 5 | **Product Flywheel** | Does the asset have compounding moats and network effects? | All |
| 6 | **Leadership** | Is management capable, aligned, and executing well? | Equities only |

The **Overall Assessment** synthesises all scored sections into a verdict (Strong Buy / Buy / Hold / Sell / Strong Sell), a 12-month price target, key drivers, and key risks. For non-equity assets with 4 sections, raw scores are scaled up to the 0–30 range so verdict thresholds remain consistent.

## How scores are generated

Every section follows a **Celery fire-and-forget** pattern:

1. User visits the asset page → HTMX fires GET requests for each report card section
2. If a fresh cached score exists → return the scored card immediately
3. If stale or missing → enqueue a Celery task, return a loading skeleton
4. HTMX polls every 6s until the score lands
5. Distributed locks (`cache.add()`) prevent duplicate agent runs for the same asset

### Agent grounding

All agents receive standardised grounding context appended to their prompts via `analyst/grounding.py`:
- Current date for temporal awareness
- Response standards: direct tone, no hedging, present tense, institutional research quality

Grounding is **appended** (not prepended) to maximise KV-cache reuse when the same grounding block appears across calls with different lead-in content.

### Section details

#### Financial Health
- **Agent:** `analyst/agents/financial_health_agent.py` — structured output (`FinancialHealthAssessment`: score, label, brief, strengths, concerns)
- **Data:** `Fundamental` model — revenue, revenue growth, earnings growth, profit margin, EPS, FCF, D/E, current ratio, ROE, dividend yield, market cap, beta, P/B
- **Prompt includes** S&P 500 benchmarks for context
- **Invalidation:** Fingerprint-driven. MD5 of all fundamental values compared against cached hash — regenerates only when data changes

#### Sentiment
- **Agent:** `analyst/agents/sentiment_agent.py` — structured output (score, label, brief, themes/factors)
- **Data:** Reddit posts, HN posts, news articles (community posts)
- **Normalisation:** Raw -1 (bearish) to 1 (bullish) → converted to 0..5 via `(score + 1) * 2.5`
- **Invalidation:** Source fingerprint (MD5 of post IDs) + 12-hour freshness TTL

#### External Risk
- **Agent:** `analyst/agents/external_risk_agent.py` — structured output (score, label, brief, risk_factors)
- **Data:** Web search for macro, regulatory, geopolitical risks
- **Invalidation:** Time-based freshness TTL

#### Valuation
- **Agent:** `analyst/agents/valuation_agent.py` — structured output (score, label, brief, bull_case, bear_case)
- **Data:** Fundamentals + web search for comparable valuations
- **Invalidation:** Fingerprint-driven (same as Financial Health)

#### Product Flywheel
- **Agent:** `analyst/agents/product_flywheel_agent.py` — structured output (score, label, brief, moat_strengths, moat_risks)
- **Data:** Web search for business model analysis
- **Invalidation:** Time-based freshness TTL

#### Leadership
- **Agent:** `analyst/agents/leadership_agent.py` — structured output (score, label, brief, strengths, risks)
- **Data:** Web search for management team analysis
- **Invalidation:** Time-based freshness TTL

#### Overall Assessment
- **Agent:** `analyst/agents/overall_assessment_agent.py` — structured output (score, label, verdict, justification, target_price, key_drivers, key_risks)
- **Data:** All scored section results + their briefs, fed as context
- **Trigger:** Only runs after all applicable sections have scores (6 for equities, 4 for others)
- **Invalidation:** Composite fingerprint of all section scores

## Company Description

Each asset gets a 1-2 sentence Bloomberg-style description generated by a dedicated LLM agent with web search:
- **Agent:** `analyst/agents/description_agent.py`
- **Manager:** `analyst/managers/description_manager.py`
- **Storage:** Persisted to `Asset.description` in the database (not just cache)
- **Freshness:** Regenerates after 90 days (`DESCRIPTION_FRESHNESS_DAYS`)
- **Trigger:** Generated on asset creation and lazy-loaded on page visit

## Architecture

```
User visits asset page
  │
  ├─ HTMX GET /assets/{ticker}/report-card/{section}/
  │    ├─ Cache hit + fingerprint match → return scored card
  │    └─ Cache miss or fingerprint mismatch
  │         ├─ Enqueue Celery task (fire-and-forget)
  │         ├─ Return loading skeleton
  │         └─ HTMX polls every 6s until score lands
  │
  ├─ Overall Assessment
  │    ├─ Waits for all applicable sections (6 equity, 4 others)
  │    └─ Synthesises into verdict + price target
  │
  └─ Company Description
       ├─ Served from DB if fresh (<90 days)
       └─ Background Celery task if stale/missing
```

## Visual design

Report cards render in a 3-column CSS grid with equal-height cards. Each scored card has:
- Compact score/label header
- Structured factor rows with subtle copper/muted vertical bar accents (not coloured pills)
- Factors capped at 5 items per list (`|slice:":5"`)
- Bottom section pushed down with `mt-auto` so cards align regardless of content length

## Key files

| File | Purpose |
|------|---------|
| `analyst/agents/*.py` | Agent definitions (one per section + description) |
| `analyst/managers/*.py` | Orchestration, caching, fingerprinting (one per section) |
| `analyst/grounding.py` | Shared grounding context for all agents |
| `analyst/app_behaviour.py` | TTL constants, freshness thresholds, truncation limits |
| `analyst/tasks.py` | Celery task definitions |
| `core/views.py` | HTMX endpoints and main view context |
| `core/templates/core/partials/report_card_*.html` | Section partials (3 states: loading, scored, unavailable) |
| `core/templates/core/asset_detail.html` | Report card grid layout |
| `scraper/clients/yfinance_client.py` | Fundamental data fetching |
| `scraper/tasks.py` | Scheduled data sync tasks |
