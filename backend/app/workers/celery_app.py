from celery import Celery

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
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Beat schedule - hourly scraping
celery_app.conf.beat_schedule = {
    "scrape-general-news": {
        "task": "app.workers.scrape_tasks.scrape_by_category",
        "schedule": settings.SCRAPE_INTERVAL_MINUTES * 60,
        "args": ["general"],
    },
    "scrape-finance-news": {
        "task": "app.workers.scrape_tasks.scrape_by_category",
        "schedule": settings.SCRAPE_INTERVAL_MINUTES * 60,
        "args": ["finance"],
    },
    "cleanup-old-articles": {
        "task": "app.workers.scrape_tasks.cleanup_old_articles",
        "schedule": 86400.0,  # Daily
    },
}

celery_app.autodiscover_tasks(["app.workers"])
