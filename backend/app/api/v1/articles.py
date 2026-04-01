import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.source import Source
from app.schemas.article import ArticleListResponse, ArticleResponse
from app.services.article_service import (
    get_article_by_id,
    get_articles,
    get_trending_articles,
)

router = APIRouter()


@router.get("", response_model=ArticleListResponse)
async def list_articles(
    source: str | None = None,
    category: str | None = None,
    source_category: str | None = None,
    search: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    articles, total = await get_articles(
        db,
        source_slug=source,
        category=category,
        source_category=source_category,
        search=search,
        from_date=from_date,
        to_date=to_date,
        page=page,
        per_page=per_page,
    )

    # Enrich with source info
    items = []
    for article in articles:
        data = ArticleResponse.model_validate(article)
        if article.source:
            data.source_name = article.source.name
            data.source_slug = article.source.slug
            data.has_paywall = article.source.has_paywall
        items.append(data)

    return ArticleListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0,
    )


@router.get("/trending", response_model=list[ArticleResponse])
async def trending_articles(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    articles = await get_trending_articles(db, hours=hours, limit=limit)
    items = []
    for article in articles:
        data = ArticleResponse.model_validate(article)
        if article.source:
            data.source_name = article.source.name
            data.source_slug = article.source.slug
            data.has_paywall = article.source.has_paywall
        items.append(data)
    return items


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: str,
    db: AsyncSession = Depends(get_db),
):
    article = await get_article_by_id(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    data = ArticleResponse.model_validate(article)
    if article.source:
        data.source_name = article.source.name
        data.source_slug = article.source.slug
        data.has_paywall = article.source.has_paywall
    return data
