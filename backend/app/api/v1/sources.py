from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.article import Article
from app.models.source import Source
from app.schemas.source import SourceResponse, SourceUpdate, SourceWithStats
from app.workers.scrape_tasks import scrape_by_category, scrape_single

router = APIRouter()


@router.get("", response_model=list[SourceWithStats])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).order_by(Source.name))
    sources = list(result.scalars().all())

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    response = []

    for source in sources:
        # Count today's articles
        today_count = await db.execute(
            select(func.count()).where(
                Article.source_id == source.id,
                Article.created_at >= today,
            )
        )
        total_count = await db.execute(
            select(func.count()).where(Article.source_id == source.id)
        )

        data = SourceWithStats.model_validate(source)
        data.articles_today = today_count.scalar() or 0
        data.total_articles = total_count.scalar() or 0
        response.append(data)

    return response


@router.get("/{slug}", response_model=SourceWithStats)
async def get_source(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).where(Source.slug == slug))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.execute(
        select(func.count()).where(
            Article.source_id == source.id,
            Article.created_at >= today,
        )
    )
    total_count = await db.execute(
        select(func.count()).where(Article.source_id == source.id)
    )

    data = SourceWithStats.model_validate(source)
    data.articles_today = today_count.scalar() or 0
    data.total_articles = total_count.scalar() or 0
    return data


@router.patch("/{slug}", response_model=SourceResponse)
async def update_source(
    slug: str,
    update: SourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Source).where(Source.slug == slug))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(source, field, value)

    await db.flush()
    return SourceResponse.model_validate(source)


@router.post("/scrape/trigger")
async def trigger_scrape(
    source_slug: str | None = None,
    category: str | None = None,
):
    """Manually trigger a scrape."""
    if source_slug:
        scrape_single.delay(source_slug)
        return {"message": f"Scrape triggered for {source_slug}"}
    elif category:
        scrape_by_category.delay(category)
        return {"message": f"Scrape triggered for category: {category}"}
    else:
        scrape_by_category.delay("general")
        scrape_by_category.delay("finance")
        return {"message": "Scrape triggered for all sources"}
