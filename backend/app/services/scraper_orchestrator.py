import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scrape_run import ScrapeRun
from app.models.source import Source
from app.scrapers.factory import get_scraper
from app.services.article_service import article_exists, create_article

logger = logging.getLogger(__name__)


async def scrape_source(db: AsyncSession, source: Source) -> ScrapeRun:
    """Scrape a single source and record the run."""
    run = ScrapeRun(
        source_id=source.id,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(run)
    await db.flush()

    try:
        scraper = get_scraper(source)
        articles = await scraper.fetch_articles()

        run.articles_found = len(articles)
        new_count = 0
        updated_count = 0

        for article_data in articles:
            if await article_exists(db, article_data["url"]):
                continue

            await create_article(
                db,
                source_id=source.id,
                source_category=source.category,
                **article_data,
            )
            new_count += 1

        run.articles_new = new_count
        run.articles_updated = updated_count
        run.status = "completed"

        source.last_scraped_at = datetime.utcnow()

    except Exception as e:
        logger.error(f"Error scraping {source.slug}: {e}")
        run.status = "failed"
        run.error_message = str(e)

    run.completed_at = datetime.utcnow()
    run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

    await db.flush()
    return run


async def scrape_all_sources(db: AsyncSession, category: str | None = None) -> list[ScrapeRun]:
    """Scrape all active sources, optionally filtered by category."""
    query = select(Source).where(Source.is_active.is_(True))
    if category:
        query = query.where(Source.category == category)

    result = await db.execute(query)
    sources = list(result.scalars().all())

    runs = []
    for source in sources:
        run = await scrape_source(db, source)
        runs.append(run)

    return runs
