import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scrape_run import ScrapeRun
from app.models.source import Source
from app.scrapers.factory import get_scraper
from app.services.article_service import create_article, existing_url_hashes, hash_url

logger = logging.getLogger(__name__)


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def scrape_source(db: AsyncSession, source: Source) -> ScrapeRun:
    """Scrape a single source and record the run."""
    logger.info("Scrape started for %s (%s)", source.name, source.slug)
    run = ScrapeRun(
        source_id=source.id,
        source_name_snapshot=source.name,
        source_slug_snapshot=source.slug,
        source_category_snapshot=source.category,
        status="running",
        started_at=utcnow_naive(),
    )
    db.add(run)
    await db.flush()

    try:
        scraper = get_scraper(source)
        articles = await scraper.fetch_articles()

        run.articles_found = len(articles)
        scraper_stats = getattr(scraper, "last_fetch_stats", None) or {}
        run.discovery_method_used = scraper_stats.get("discovery_method_used")
        run.detail_enriched_count = scraper_stats.get("detail_enriched_count", 0)
        run.metadata_only_count = scraper_stats.get("metadata_only_count", len(articles))
        new_count = 0
        updated_count = 0
        known_hashes = await existing_url_hashes(
            db,
            [article.get("url", "") for article in articles],
        )

        for article_data in articles:
            article_url = article_data.get("url")
            if not article_url:
                continue

            article_hash = hash_url(article_url)
            if article_hash and article_hash in known_hashes:
                continue

            await create_article(
                db,
                source_id=source.id,
                source_category=source.category,
                **article_data,
            )
            known_hashes.add(article_hash)
            new_count += 1

        run.articles_new = new_count
        run.articles_updated = updated_count
        run.status = "completed"

        source.last_scraped_at = utcnow_naive()

    except Exception as e:
        logger.error(f"Error scraping {source.slug}: {e}")
        run.status = "failed"
        run.error_message = str(e)

    run.completed_at = utcnow_naive()
    run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

    await db.flush()
    logger.info(
        "Scrape finished for %s (%s): status=%s found=%s new=%s method=%s duration=%.1fs",
        source.name,
        source.slug,
        run.status,
        run.articles_found,
        run.articles_new,
        run.discovery_method_used or "-",
        run.duration_seconds or 0.0,
    )
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
