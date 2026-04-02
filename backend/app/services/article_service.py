import hashlib
import math
from uuid import UUID
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.article import Article
from app.models.source import Source
from app.scrapers.article_detail import ArticleDetailEnricher
from app.services.article_visibility import apply_article_visibility_filters, article_is_visible


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
    query = apply_article_visibility_filters(
        select(Article).join(Source).options(selectinload(Article.source))
    )

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
    try:
        normalized_id = UUID(str(article_id))
    except (TypeError, ValueError):
        return None
    result = await db.execute(
        select(Article)
        .join(Source)
        .where(Article.id == normalized_id)
        .where(Source.is_active.is_(True))
        .options(selectinload(Article.source))
    )
    article = result.scalar_one_or_none()
    if article is None or not article_is_visible(article):
        return None
    return article


def article_to_enrichment_payload(article: Article) -> dict[str, Any]:
    return {
        "title": article.title,
        "url": article.url,
        "summary": article.summary,
        "content_snippet": article.content_snippet,
        "content_text": article.content_text,
        "author": article.author,
        "published_at": article.published_at,
        "image_url": article.image_url,
        "category": article.category,
        "tags": article.tags,
        "raw_metadata": dict(article.raw_metadata or {}),
    }


def merge_enriched_article(article: Article, enriched: dict[str, Any], *, changed: bool, attempted_at: datetime) -> None:
    for field in (
        "title",
        "summary",
        "content_snippet",
        "content_text",
        "author",
        "published_at",
        "image_url",
        "category",
        "tags",
    ):
        value = enriched.get(field)
        if value not in (None, "", [], {}):
            setattr(article, field, value)

    raw_metadata = dict(enriched.get("raw_metadata") or article.raw_metadata or {})
    detail_enrichment = dict(raw_metadata.get("detail_enrichment") or {})
    detail_enrichment.setdefault("status", "success")
    detail_enrichment.setdefault("changed", changed)
    detail_enrichment.setdefault("fetched_at", attempted_at.isoformat())
    raw_metadata["detail_enriched"] = changed
    raw_metadata["detail_enrichment"] = detail_enrichment
    article.raw_metadata = raw_metadata
    article.detail_enriched = bool(article.content_text)
    article.detail_fetched_at = attempted_at


def record_detail_enrichment_state(
    article: Article,
    *,
    status: str,
    attempted_at: datetime | None = None,
    error: str | None = None,
) -> None:
    raw_metadata = dict(article.raw_metadata or {})
    detail_enrichment = {
        "status": status,
        "changed": False,
        "error": error,
    }
    if attempted_at is not None:
        detail_enrichment["fetched_at"] = attempted_at.isoformat()
    raw_metadata["detail_enriched"] = bool(article.content_text)
    raw_metadata["detail_enrichment"] = detail_enrichment
    article.raw_metadata = raw_metadata
    article.detail_enriched = bool(article.content_text)
    if attempted_at is not None:
        article.detail_fetched_at = attempted_at


async def enrich_article_detail_if_needed(db: AsyncSession, article: Article) -> Article:
    source = article.source
    if source is None:
        return article
    if article.content_text and article.detail_enriched:
        return article
    if article.detail_fetched_at is not None:
        return article
    if source.has_paywall:
        record_detail_enrichment_state(article, status="skipped_paywall")
        await db.flush()
        return article

    detail_policy = (source.config or {}).get("detail_policy", "open_page_only")
    if detail_policy != "open_page_only":
        record_detail_enrichment_state(article, status="skipped_policy")
        await db.flush()
        return article

    enricher = ArticleDetailEnricher(source)
    if enricher.should_skip_url(article.url):
        record_detail_enrichment_state(article, status="skipped_url")
        await db.flush()
        return article
    payload = article_to_enrichment_payload(article)
    if not enricher.needs_enrichment(payload, include_content_text=True):
        return article
    if not await enricher.is_allowed(article.url):
        record_detail_enrichment_state(
            article,
            status="blocked_by_robots",
            attempted_at=utcnow(),
        )
        await db.flush()
        return article

    attempted_at = utcnow()
    try:
        enriched, changed = await enricher.enrich_article(payload)
    except Exception as exc:  # pragma: no cover - defensive logging path
        record_detail_enrichment_state(
            article,
            status="failed",
            attempted_at=attempted_at,
            error=str(exc)[:500],
        )
        await db.flush()
        return article

    merge_enriched_article(article, enriched, changed=changed, attempted_at=attempted_at)
    await db.flush()
    await db.refresh(article)
    return article


async def article_exists(db: AsyncSession, url: str) -> bool:
    """Check if article already exists by URL hash."""
    url_h = hash_url(url)
    result = await db.execute(
        select(func.count()).where(Article.url_hash == url_h)
    )
    return (result.scalar() or 0) > 0


async def existing_url_hashes(db: AsyncSession, urls: list[str]) -> set[str]:
    """Return URL hashes that already exist for a batch of article URLs."""
    if not urls:
        return set()

    hashed_urls = {hash_url(url) for url in urls if url}
    if not hashed_urls:
        return set()

    result = await db.execute(
        select(Article.url_hash).where(Article.url_hash.in_(hashed_urls))
    )
    return {row[0] for row in result.all() if row[0]}


async def create_article(db: AsyncSession, **kwargs) -> Article:
    """Create article with automatic URL hashing."""
    kwargs["url_hash"] = hash_url(kwargs["url"])
    kwargs.setdefault("scraped_at", utcnow())
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
    cutoff = utcnow() - timedelta(hours=hours)
    query = apply_article_visibility_filters(
        select(Article)
        .join(Source)
        .options(selectinload(Article.source))
        .where(Article.published_at >= cutoff)
    )
    query = query.order_by(Article.published_at.desc()).limit(limit)
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
