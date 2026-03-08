# Tidalsight

A Django web application.

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
| `sync_all_asset_prices` | Every hour | Sync hourly + daily prices for all active assets (hourly due to 24/7 crypto markets) |
| `sync_all_asset_fundamentals` | Daily at 6:00 UTC (Mon–Fri) | Refresh fundamentals for all active assets |
| `fetch_reddit` | Every 2 hours | Scrape 18 financial subreddits for ticker mentions |
| `fetch_hn` | Every 4 hours | Fetch top Hacker News stories and match to assets |
| `fetch_news` | Every 6 hours | Fetch news articles from Brave News Search |

The Celery worker runs as a separate Railway service using `celery_railway.json`. Task results are persisted to Postgres via `django-celery-results` and viewable in Django admin.

### Backfill

| Command | Description |
|---|---|
| `backfill_embeddings` | Generate embeddings for all Reddit posts, HN posts, and news articles missing one. Supports `--batch-size` option. |
| `backfill_fundamentals` | Re-fetch fundamentals for all active assets to populate new fields. Supports `--delay` to throttle API calls. |
| `backfill_peers` | Discover and backfill peer/competitor assets via LLM for all active assets missing peers. Supports `--ticker` to target a single asset and `--force` to re-discover existing peers. |
