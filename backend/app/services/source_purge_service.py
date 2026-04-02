from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.scrape_run import ScrapeRun
from app.models.source import Source


async def purge_sources_by_slug(
    db: AsyncSession,
    slugs: tuple[str, ...] | list[str],
) -> dict[str, object]:
    result = await db.execute(
        select(Source).where(Source.slug.in_(list(slugs))).order_by(Source.slug.asc())
    )
    sources = list(result.scalars().all())

    deleted_sources: list[str] = []
    total_articles_deleted = 0
    total_runs_detached = 0

    for source in sources:
        detached_runs = await db.execute(
            update(ScrapeRun)
            .where(ScrapeRun.source_id == source.id)
            .values(
                source_id=None,
                source_name_snapshot=func.coalesce(ScrapeRun.source_name_snapshot, source.name),
                source_slug_snapshot=func.coalesce(ScrapeRun.source_slug_snapshot, source.slug),
                source_category_snapshot=func.coalesce(ScrapeRun.source_category_snapshot, source.category),
            )
        )
        total_runs_detached += detached_runs.rowcount or 0

        deleted_articles = await db.execute(
            delete(Article).where(Article.source_id == source.id)
        )
        total_articles_deleted += deleted_articles.rowcount or 0

        deleted_sources.append(source.slug)
        await db.delete(source)

    await db.flush()
    return {
        "deleted_slugs": deleted_sources,
        "sources_deleted": len(deleted_sources),
        "articles_deleted": total_articles_deleted,
        "runs_detached": total_runs_detached,
    }
