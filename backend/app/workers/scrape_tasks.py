import asyncio
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.db.session import async_session_factory
from app.models.article import Article
from app.models.source import Source
from app.config import settings
from app.services.scraper_orchestrator import scrape_all_sources, scrape_source
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async function in sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def get_retention_cutoff(*, now: datetime | None = None, retention_hours: int | None = None) -> tuple[datetime, datetime]:
    tz = ZoneInfo(settings.APP_TIMEZONE)
    retention_window = retention_hours or settings.ARTICLE_RETENTION_HOURS

    if now is None:
        current_local = datetime.now(tz)
    elif now.tzinfo is None:
        current_local = now.replace(tzinfo=UTC).astimezone(tz)
    else:
        current_local = now.astimezone(tz)

    midnight_local = current_local.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_local = midnight_local - timedelta(hours=retention_window)
    cutoff_utc_naive = cutoff_local.astimezone(UTC).replace(tzinfo=None)
    return cutoff_local, cutoff_utc_naive


async def delete_articles_before(db, cutoff_utc_naive: datetime) -> int:
    result = await db.execute(
        delete(Article).where(Article.created_at < cutoff_utc_naive)
    )
    await db.commit()
    return result.rowcount or 0


@celery_app.task(name="app.workers.scrape_tasks.scrape_by_category")
def scrape_by_category(category: str):
    """Scrape all active sources in a category."""
    logger.info(f"Starting scrape for category: {category}")

    async def _scrape():
        async with async_session_factory() as db:
            runs = await scrape_all_sources(db, category=category)
            await db.commit()
            return len(runs)

    count = run_async(_scrape())
    logger.info(f"Completed scrape for {category}: {count} sources processed")
    return {"category": category, "sources_processed": count}


@celery_app.task(name="app.workers.scrape_tasks.scrape_all_active_sources")
def scrape_all_active_sources():
    """Scrape all active sources once per hourly scheduler tick."""
    logger.info("Starting hourly scrape for all active sources")

    async def _scrape():
        async with async_session_factory() as db:
            runs = await scrape_all_sources(db)
            await db.commit()
            return len(runs)

    count = run_async(_scrape())
    logger.info("Completed hourly scrape for all active sources: %s sources processed", count)
    return {"sources_processed": count}


@celery_app.task(name="app.workers.scrape_tasks.scrape_single")
def scrape_single(source_slug: str):
    """Scrape a single source by slug."""
    logger.info(f"Starting scrape for source: {source_slug}")

    async def _scrape():
        async with async_session_factory() as db:
            result = await db.execute(
                select(Source).where(Source.slug == source_slug)
            )
            source = result.scalar_one_or_none()
            if not source:
                raise ValueError(f"Source not found: {source_slug}")

            run = await scrape_source(db, source)
            await db.commit()
            return {
                "source": source_slug,
                "status": run.status,
                "articles_found": run.articles_found,
                "articles_new": run.articles_new,
            }

    return run_async(_scrape())


@celery_app.task(name="app.workers.scrape_tasks.cleanup_retained_articles")
def cleanup_retained_articles(retention_hours: int = settings.ARTICLE_RETENTION_HOURS):
    """Remove retained articles older than the local-midnight retention cutoff."""
    cutoff_local, cutoff_utc_naive = get_retention_cutoff(retention_hours=retention_hours)
    logger.info(
        "Cleaning up retained articles at local midnight window: timezone=%s cutoff_local=%s cutoff_utc=%s",
        settings.APP_TIMEZONE,
        cutoff_local.isoformat(),
        cutoff_utc_naive.isoformat(),
    )

    async def _cleanup():
        async with async_session_factory() as db:
            return await delete_articles_before(db, cutoff_utc_naive)

    deleted = run_async(_cleanup())
    logger.info("Deleted %s retained articles older than cutoff %s", deleted, cutoff_utc_naive.isoformat())
    return {
        "deleted": deleted,
        "cutoff_local": cutoff_local.isoformat(),
        "cutoff_utc": cutoff_utc_naive.isoformat(),
    }


@celery_app.task(name="app.workers.scrape_tasks.cleanup_old_articles")
def cleanup_old_articles(days: int = 30):
    """Backward-compatible alias for retained article cleanup."""
    return cleanup_retained_articles(retention_hours=settings.ARTICLE_RETENTION_HOURS)
