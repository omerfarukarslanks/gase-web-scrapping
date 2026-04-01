from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.article import Article
from app.models.scrape_run import ScrapeRun
from app.models.source import Source
from app.schemas.scrape_run import DashboardStats, ScrapeRunResponse
from app.services.article_service import get_articles_count_by_source

router = APIRouter()


@router.get("", response_model=list[ScrapeRunResponse])
async def list_scrape_runs(
    source_slug: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(ScrapeRun).join(Source).options(selectinload(ScrapeRun.source)).order_by(ScrapeRun.started_at.desc()).limit(limit)

    if source_slug:
        query = query.where(Source.slug == source_slug)

    result = await db.execute(query)
    runs = list(result.scalars().all())

    items = []
    for run in runs:
        data = ScrapeRunResponse.model_validate(run)
        if run.source:
            data.source_name = run.source.name
            data.source_slug = run.source.slug
        items.append(data)

    return items


@router.get("/latest", response_model=list[ScrapeRunResponse])
async def latest_scrape_runs(db: AsyncSession = Depends(get_db)):
    """Get the latest scrape run for each source."""
    # Subquery to get max started_at per source
    subquery = (
        select(
            ScrapeRun.source_id,
            func.max(ScrapeRun.started_at).label("max_started"),
        )
        .group_by(ScrapeRun.source_id)
        .subquery()
    )

    query = (
        select(ScrapeRun)
        .join(Source)
        .join(
            subquery,
            (ScrapeRun.source_id == subquery.c.source_id)
            & (ScrapeRun.started_at == subquery.c.max_started),
        )
        .order_by(Source.name)
    )

    result = await db.execute(query)
    runs = list(result.scalars().all())

    items = []
    for run in runs:
        data = ScrapeRunResponse.model_validate(run)
        if run.source:
            data.source_name = run.source.name
            data.source_slug = run.source.slug
        items.append(data)

    return items


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics."""
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Total articles
    total = await db.execute(select(func.count()).select_from(Article))
    total_articles = total.scalar() or 0

    # Today's articles
    today_count = await db.execute(
        select(func.count()).where(Article.created_at >= today)
    )
    articles_today = today_count.scalar() or 0

    # Sources
    active_sources = await db.execute(
        select(func.count()).where(Source.is_active.is_(True))
    )
    total_sources = await db.execute(select(func.count()).select_from(Source))

    # Last scrape
    last_scrape = await db.execute(
        select(func.max(ScrapeRun.completed_at))
    )

    # Articles by source (today)
    articles_by_source = await get_articles_count_by_source(db, since=today)

    # Articles by category (today)
    cat_query = (
        select(Article.source_category, func.count(Article.id).label("count"))
        .where(Article.created_at >= today)  # type: ignore[arg-type]
        .group_by(Article.source_category)
    )
    cat_result = await db.execute(cat_query)
    articles_by_category = [
        {"category": r[0], "count": r[1]} for r in cat_result.all()
    ]

    # Recent runs
    runs_query = (
        select(ScrapeRun)
        .join(Source)
        .options(selectinload(ScrapeRun.source))
        .order_by(ScrapeRun.started_at.desc())
        .limit(10)
    )
    runs_result = await db.execute(runs_query)
    recent_runs = []
    for run in runs_result.scalars().all():
        data = ScrapeRunResponse.model_validate(run)
        if run.source:
            data.source_name = run.source.name
            data.source_slug = run.source.slug
        recent_runs.append(data)

    return DashboardStats(
        total_articles=total_articles,
        articles_today=articles_today,
        active_sources=active_sources.scalar() or 0,
        total_sources=total_sources.scalar() or 0,
        last_scrape_at=last_scrape.scalar(),
        articles_by_source=articles_by_source,
        articles_by_category=articles_by_category,
        recent_runs=recent_runs,
    )
