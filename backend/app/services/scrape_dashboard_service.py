from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.scrape_run import ScrapeRun
from app.models.source import Source


def now_local() -> datetime:
    return datetime.now(ZoneInfo(settings.APP_TIMEZONE))


def start_of_local_day_utc_naive(now: datetime | None = None) -> datetime:
    current = now or now_local()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC).astimezone(ZoneInfo(settings.APP_TIMEZONE))
    else:
        current = current.astimezone(ZoneInfo(settings.APP_TIMEZONE))
    local_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(UTC).replace(tzinfo=None)


def get_scrape_run_identity(run: ScrapeRun) -> tuple[str | None, str | None, str | None]:
    if run.source is not None:
        return run.source.name, run.source.slug, run.source.category
    return run.source_name_snapshot, run.source_slug_snapshot, run.source_category_snapshot


async def build_dashboard_metrics(db: AsyncSession) -> dict:
    today_cutoff = start_of_local_day_utc_naive()
    completed_filter = ScrapeRun.status == "completed"

    total_articles_result = await db.execute(
        select(func.coalesce(func.sum(ScrapeRun.articles_new), 0)).where(completed_filter)
    )
    today_articles_result = await db.execute(
        select(func.coalesce(func.sum(ScrapeRun.articles_new), 0)).where(
            completed_filter,
            ScrapeRun.completed_at >= today_cutoff,
        )
    )

    active_sources = await db.execute(
        select(func.count()).where(Source.is_active.is_(True))
    )
    total_sources = await db.execute(select(func.count()).select_from(Source))
    last_scrape = await db.execute(
        select(func.max(ScrapeRun.completed_at)).where(completed_filter)
    )

    source_name_expr = func.coalesce(ScrapeRun.source_name_snapshot, Source.name)
    source_slug_expr = func.coalesce(ScrapeRun.source_slug_snapshot, Source.slug)
    source_category_expr = func.coalesce(ScrapeRun.source_category_snapshot, Source.category)

    articles_by_source_result = await db.execute(
        select(
            source_name_expr.label("name"),
            source_slug_expr.label("slug"),
            func.coalesce(func.sum(ScrapeRun.articles_new), 0).label("count"),
        )
        .select_from(ScrapeRun)
        .outerjoin(Source, ScrapeRun.source_id == Source.id)
        .where(
            completed_filter,
            ScrapeRun.completed_at >= today_cutoff,
            source_name_expr.is_not(None),
            source_slug_expr.is_not(None),
        )
        .group_by(source_name_expr, source_slug_expr)
        .order_by(func.sum(ScrapeRun.articles_new).desc(), source_name_expr.asc())
    )
    articles_by_source = [
        {"name": row.name, "slug": row.slug, "count": row.count}
        for row in articles_by_source_result.all()
    ]

    articles_by_category_result = await db.execute(
        select(
            source_category_expr.label("category"),
            func.coalesce(func.sum(ScrapeRun.articles_new), 0).label("count"),
        )
        .select_from(ScrapeRun)
        .outerjoin(Source, ScrapeRun.source_id == Source.id)
        .where(
            completed_filter,
            ScrapeRun.completed_at >= today_cutoff,
            source_category_expr.is_not(None),
        )
        .group_by(source_category_expr)
        .order_by(func.sum(ScrapeRun.articles_new).desc(), source_category_expr.asc())
    )
    articles_by_category = [
        {"category": row.category, "count": row.count}
        for row in articles_by_category_result.all()
    ]

    recent_runs_result = await db.execute(
        select(ScrapeRun)
        .outerjoin(Source, ScrapeRun.source_id == Source.id)
        .options(selectinload(ScrapeRun.source))
        .order_by(ScrapeRun.started_at.desc())
        .limit(10)
    )
    recent_runs = list(recent_runs_result.scalars().all())

    return {
        "total_articles": int(total_articles_result.scalar() or 0),
        "articles_today": int(today_articles_result.scalar() or 0),
        "active_sources": int(active_sources.scalar() or 0),
        "total_sources": int(total_sources.scalar() or 0),
        "last_scrape_at": last_scrape.scalar(),
        "articles_by_source": articles_by_source,
        "articles_by_category": articles_by_category,
        "recent_runs": recent_runs,
    }
