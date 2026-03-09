import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    f"tidalsight.settings.{os.environ['ENV_TYPE']}",
)

app = Celery("tidalsight")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# IMPORTANT: Do not add scheduled tasks that make LLM/AI calls across all assets.
# With 2k+ assets, even a single AI call per asset on a cron will be extremely
# expensive. AI-powered features (sentiment, peer discovery) should remain
# on-demand via user visits. If a scheduled AI task is truly needed, scope it
# as narrowly as possible (e.g. a single global digest, not per-asset).
app.conf.beat_schedule = {
    "fetch Reddit posts every 2 hours": {
        "task": "scraper.tasks.fetch_reddit",
        "schedule": crontab(minute=0, hour="*/2"),
    },
    "fetch HN posts every 4 hours": {
        "task": "scraper.tasks.fetch_hn",
        "schedule": crontab(minute=15, hour="*/4"),
    },
    "fetch news every 6 hours": {
        "task": "scraper.tasks.fetch_news",
        "schedule": crontab(minute=30, hour="*/6"),
    },
    "sync prices hourly": {
        "task": "scraper.tasks.sync_all_asset_prices",
        "schedule": crontab(minute=45),
    },
    "sync fundamentals daily on weekdays": {
        "task": "scraper.tasks.sync_all_asset_fundamentals",
        "schedule": crontab(minute=0, hour=6, day_of_week="1-5"),
    },
    "refresh market digest hourly": {
        "task": "analyst.tasks.generate_market_digest",
        "schedule": crontab(minute=50),
    },
}
