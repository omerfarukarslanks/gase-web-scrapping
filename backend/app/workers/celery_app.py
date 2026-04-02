from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "news_scraper",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.APP_TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule_filename="/tmp/celerybeat-schedule-v2",
)

# Beat schedule
celery_app.conf.beat_schedule = {
    "scrape-all-sources": {
        "task": "app.workers.scrape_tasks.scrape_all_active_sources",
        "schedule": crontab(minute=0),
    },
    "cleanup-retained-articles": {
        "task": "app.workers.scrape_tasks.cleanup_retained_articles",
        "schedule": crontab(minute=0, hour=0),
    },
}

celery_app.autodiscover_tasks(["app.workers"])
