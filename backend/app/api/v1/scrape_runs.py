from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.scrape_run import ScrapeRun
from app.models.source import Source
from app.schemas.scrape_run import DashboardStats, ScrapeRunResponse
from app.services.scrape_dashboard_service import build_dashboard_metrics, get_scrape_run_identity

router = APIRouter()


def hydrate_scrape_run_response(run: ScrapeRun) -> ScrapeRunResponse:
    data = ScrapeRunResponse.model_validate(run)
    source_name, source_slug, _source_category = get_scrape_run_identity(run)
    data.source_name = source_name
    data.source_slug = source_slug
    return data


@router.get("", response_model=list[ScrapeRunResponse])
async def list_scrape_runs(
    source_slug: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ScrapeRun)
        .outerjoin(Source)
        .options(selectinload(ScrapeRun.source))
        .order_by(ScrapeRun.started_at.desc())
        .limit(limit)
    )

    if source_slug:
        query = query.where(
            or_(Source.slug == source_slug, ScrapeRun.source_slug_snapshot == source_slug)
        )

    result = await db.execute(query)
    runs = list(result.scalars().all())

    return [hydrate_scrape_run_response(run) for run in runs]


@router.get("/latest", response_model=list[ScrapeRunResponse])
async def latest_scrape_runs(db: AsyncSession = Depends(get_db)):
    """Get the latest scrape run for each source."""
    query = (
        select(ScrapeRun)
        .outerjoin(Source)
        .options(selectinload(ScrapeRun.source))
        .order_by(ScrapeRun.started_at.desc())
    )
    result = await db.execute(query)
    runs = list(result.scalars().all())

    items: list[ScrapeRunResponse] = []
    seen_keys: set[str] = set()
    for run in runs:
        source_name, source_slug, _source_category = get_scrape_run_identity(run)
        identity = source_slug or source_name or str(run.id)
        if identity in seen_keys:
            continue
        seen_keys.add(identity)
        items.append(hydrate_scrape_run_response(run))

    return sorted(items, key=lambda item: ((item.source_name or "").lower(), item.started_at), reverse=False)


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics."""
    metrics = await build_dashboard_metrics(db)
    recent_runs = [hydrate_scrape_run_response(run) for run in metrics["recent_runs"]]

    return DashboardStats(
        total_articles=metrics["total_articles"],
        articles_today=metrics["articles_today"],
        active_sources=metrics["active_sources"],
        total_sources=metrics["total_sources"],
        last_scrape_at=metrics["last_scrape_at"],
        articles_by_source=metrics["articles_by_source"],
        articles_by_category=metrics["articles_by_category"],
        recent_runs=recent_runs,
    )
