import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.db.session import async_session_factory
from app.models.article import Article
from app.models.source import Source
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


@celery_app.task(name="app.workers.scrape_tasks.cleanup_old_articles")
def cleanup_old_articles(days: int = 30):
    """Remove articles older than N days."""
    logger.info(f"Cleaning up articles older than {days} days")

    async def _cleanup():
        cutoff = datetime.utcnow() - timedelta(days=days)
        async with async_session_factory() as db:
            result = await db.execute(
                delete(Article).where(Article.created_at < cutoff)
            )
            await db.commit()
            return result.rowcount

    deleted = run_async(_cleanup())
    logger.info(f"Deleted {deleted} old articles")
    return {"deleted": deleted}
