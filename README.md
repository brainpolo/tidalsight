# Tidalsight

A Django web application.

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

### Backfill

| Command | Description |
|---|---|
| `backfill_embeddings` | Generate embeddings for all Reddit posts, HN posts, and news articles missing one. Supports `--batch-size` option. |
| `backfill_fundamentals` | Re-fetch fundamentals for all active assets to populate new fields. Supports `--delay` to throttle API calls. |
| `backfill_peers` | Discover and backfill peer/competitor assets via LLM for all active assets missing peers. Supports `--ticker` to target a single asset and `--force` to re-discover existing peers. |
