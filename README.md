# Tidalsight

A real-time market intelligence platform that combines financial data, community sentiment, and AI-powered analysis into a single view per asset.

## Core Features

- **Self-expanding asset network** — The universe of tracked assets grows autonomously. When a user visits any asset, an LLM agent discovers its peers and competitors, which become first-class assets themselves. Each new asset triggers further discovery, creating an organically expanding knowledge graph seeded from a single ticker.
- **AI community sentiment** — Aggregates Reddit, Hacker News, and news articles, then runs an LLM agent to produce a sentiment score, label, brief, and key themes per asset. Fingerprinted against source posts so it only regenerates when the conversation changes.
- **AI market digest** — A global market brief synthesised from the latest community posts across all sources, regenerated hourly with the same source-fingerprint optimisation.
- **Infinite-scroll daily prices** — Cursor-based pagination streams the full price history as the user scrolls, with positive-day statistics computed across 30d/90d/1y/5y/all-time windows.
- **Interactive price chart** — Canvas-rendered chart with range switching (1D–ALL), RSI gauge, price target overlay, click-to-measure, and PNG export.
- **[AI report card](REPORT_CARD.md)** — Holistic buy/sell/hold assessment across 6 dimensions (Financial Health, Sentiment, External Risk, Valuation, Product Flywheel, Leadership) scored out of 5, synthesised into an overall verdict with a 12-month price target. Built on Herzberg's Two-Factor Theory separating hygiene factors from motivators.
- **Personalisation** — Watchlists, price targets, and private notes per asset that feed into AI-generated analysis.
- **Zero-config data pipeline** — Celery Beat continuously ingests prices, fundamentals, Reddit, Hacker News, and news. New assets get quick-synced on first visit, then backfilled in the background.

## Architecture

Three Django apps, each with a single responsibility:

- **`scraper`** — Data acquisition. Fetches and stores raw market data from external sources (yfinance, Reddit, Hacker News, Brave News). Owns all external API clients, data models (Asset, PriceHistory, Fundamental, RedditPost, HNPost, NewsArticle), and sync/staleness logic. Never renders templates or serves user-facing responses.

- **`core`** — User-facing application. Owns the UI (views, templates, URL routing), user model, authentication, watchlists, and all presentation logic. Reads from scraper's models but never calls external APIs directly. Transforms raw data into display-ready structures (fundamental cards, chart data, sparklines).

- **`analyst`** — Intelligence layer. Runs LLM-powered agents for peer discovery and market digest generation. Sits between scraper (reads raw data) and core (surfaces results). Owns agent definitions, prompt engineering, and async orchestration.

This separation means scraper can run headlessly (CLI, Celery tasks), core stays focused on rendering, and analyst encapsulates all AI complexity behind simple function calls.

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

## Run

```bash
uv run python manage.py migrate
uv run python manage.py runserver
```

The app will be available at `http://localhost:8000`.

## Management Commands

All commands are run with `uv run python manage.py <command>`.

### Data Ingestion

| Command | Description |
|---|---|
| `fetch_asset <TICKERS...>` | Fetch price history and fundamentals for one or more tickers. Supports `--skip-prices` and `--skip-fundamentals` flags. |
| `fetch_reddit` | Scrape posts from financial subreddits, store comments, generate embeddings, and link to known assets. Supports `--subreddits`, `--sort` (hot/new/top/rising), and `--limit` options. |
| `fetch_hn` | Fetch top Hacker News stories, match to known assets by keyword, store comments, and generate embeddings. |
| `fetch_news` | Fetch news articles from Brave News Search and link to assets. Supports `--query`, `--ticker` (asset-targeted mode), `--freshness` (pd/pw/pm), and `--count` options. |

## Automatic Updates

Celery Beat runs the following tasks automatically in production:

| Task | Schedule | Description |
|---|---|---|
| `sync_crypto_prices` | Every hour | Sync hourly + daily prices for crypto assets (24/7 markets) |
| `sync_traditional_prices` | Every hour (Mon–Fri) | Sync hourly + daily prices for non-crypto assets (equities, commodities, etc.) |
| `sync_all_asset_fundamentals` | Daily at 6:00 UTC (Mon–Fri) | Refresh fundamentals for all active assets |
| `fetch_reddit` | Every 2 hours | Scrape 18 financial subreddits for `$TICKER` cashtags. **Only source that creates new assets** — unrecognised tickers trigger yfinance lookup, asset creation, price/fundamental sync, and LLM peer discovery. Also generates embeddings per post. |
| `fetch_hn` | Every 4 hours | Fetch top 200 HN stories (score ≥ 10) and match to **existing** assets via keyword matching. Generates embeddings but never creates new assets. |
| `fetch_news` | Every 6 hours | Fetch 20 articles from Brave News Search and match to **existing** assets via keyword matching. Generates embeddings but never creates new assets. |
| `generate_market_digest` | Every hour | Regenerate the AI market digest (skipped if sources unchanged) |

The Celery worker runs as a separate Railway service using `celery_railway.json`. Task results are persisted to Postgres via `django-celery-results` and viewable in Django admin.

### Backfill

| Command | Description |
|---|---|
| `backfill_embeddings` | Generate embeddings for all Reddit posts, HN posts, and news articles missing one. Supports `--batch-size` option. |
| `backfill_fundamentals` | Re-fetch fundamentals for all active assets to populate new fields. Supports `--delay` to throttle API calls. |
| `backfill_peers` | Discover and backfill peer/competitor assets via LLM for all active assets missing peers. Supports `--ticker` to target a single asset and `--force` to re-discover existing peers. |
