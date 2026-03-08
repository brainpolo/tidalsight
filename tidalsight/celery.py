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

app.conf.beat_schedule = {
    "fetch HN posts every 2 hours": {
        "task": "scraper.tasks.fetch_hn",
        "schedule": crontab(minute=0, hour="*/2"),
    },
    "fetch Reddit posts every hour": {
        "task": "scraper.tasks.fetch_reddit",
        "schedule": crontab(minute=15),
    },
    "fetch news every 3 hours": {
        "task": "scraper.tasks.fetch_news",
        "schedule": crontab(minute=30, hour="*/3"),
    },
}
