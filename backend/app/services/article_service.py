import hashlib
import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.article import Article
from app.models.source import Source


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    url = url.strip().rstrip("/")
    # Remove common tracking parameters
    if "?" in url:
        base, params = url.split("?", 1)
        tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref", "fbclid", "gclid"}
        filtered = "&".join(
            p for p in params.split("&")
            if p.split("=")[0].lower() not in tracking_params
        )
        url = f"{base}?{filtered}" if filtered else base
    return url


def hash_url(url: str) -> str:
    """Generate SHA256 hash of normalized URL."""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode()).hexdigest()


async def get_articles(
    db: AsyncSession,
    *,
    source_slug: str | None = None,
    category: str | None = None,
    source_category: str | None = None,
    search: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Article], int]:
    """Get paginated articles with filters."""
    query = select(Article).join(Source).options(selectinload(Article.source))

    if source_slug:
        query = query.where(Source.slug == source_slug)
    if category:
        query = query.where(Article.category == category)
    if source_category:
        query = query.where(Article.source_category == source_category)
    if search:
        query = query.where(Article.title.ilike(f"%{search}%"))
    if from_date:
        query = query.where(Article.published_at >= from_date)
    if to_date:
        query = query.where(Article.published_at <= to_date)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(Article.published_at.desc().nullslast())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    articles = list(result.scalars().all())

    return articles, total


async def get_article_by_id(db: AsyncSession, article_id) -> Article | None:
    result = await db.execute(
        select(Article).where(Article.id == article_id)
    )
    return result.scalar_one_or_none()


async def article_exists(db: AsyncSession, url: str) -> bool:
    """Check if article already exists by URL hash."""
    url_h = hash_url(url)
    result = await db.execute(
        select(func.count()).where(Article.url_hash == url_h)
    )
    return (result.scalar() or 0) > 0


async def create_article(db: AsyncSession, **kwargs) -> Article:
    """Create article with automatic URL hashing."""
    kwargs["url_hash"] = hash_url(kwargs["url"])
    kwargs.setdefault("scraped_at", datetime.utcnow())
    article = Article(**kwargs)
    db.add(article)
    await db.flush()
    return article


async def get_trending_articles(
    db: AsyncSession,
    hours: int = 24,
    limit: int = 20,
) -> list[Article]:
    """Get articles from the last N hours, prioritizing those covered by multiple sources."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    query = (
        select(Article)
        .join(Source)
        .options(selectinload(Article.source))
        .where(Article.published_at >= cutoff)
        .order_by(Article.published_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_articles_count_by_source(
    db: AsyncSession,
    since: datetime | None = None,
) -> list[dict]:
    """Get article counts grouped by source."""
    query = (
        select(Source.name, Source.slug, func.count(Article.id).label("count"))
        .join(Article, isouter=True)
    )
    if since:
        query = query.where(Article.created_at >= since)
    query = query.group_by(Source.name, Source.slug).order_by(func.count(Article.id).desc())
    result = await db.execute(query)
    return [{"name": r[0], "slug": r[1], "count": r[2]} for r in result.all()]
