from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.scrape_run import ScrapeRun
from app.models.source import Source
from app.services.article_service import hash_url
from app.services.source_purge_service import purge_sources_by_slug


@pytest.mark.asyncio
async def test_purge_sources_by_slug_deletes_live_data_and_preserves_runs(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = Source(
        name="Reuters",
        slug="reuters",
        base_url="https://www.reuters.com",
        rss_feeds=[],
        scraper_type="rss",
        category="general",
        is_active=False,
        scrape_interval_minutes=60,
        rate_limit_rpm=10,
        has_paywall=False,
        config={},
        last_scraped_at=None,
    )
    db_session.add(source)
    await db_session.flush()

    article = Article(
        source_id=source.id,
        title="Reuters article",
        url="https://www.reuters.com/world/example-story",
        url_hash=hash_url("https://www.reuters.com/world/example-story"),
        summary="Example summary",
        published_at=now,
        scraped_at=now,
        source_category="general",
    )
    db_session.add(article)

    run = ScrapeRun(
        source_id=source.id,
        status="completed",
        articles_found=4,
        articles_new=4,
        articles_updated=0,
        detail_enriched_count=0,
        metadata_only_count=4,
        discovery_method_used="rss",
        error_message=None,
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
    )
    db_session.add(run)
    await db_session.commit()

    summary = await purge_sources_by_slug(db_session, ("reuters",))
    await db_session.commit()

    assert summary == {
        "deleted_slugs": ["reuters"],
        "sources_deleted": 1,
        "articles_deleted": 1,
        "runs_detached": 1,
    }

    source_result = await db_session.execute(select(Source).where(Source.slug == "reuters"))
    assert source_result.scalar_one_or_none() is None

    article_result = await db_session.execute(select(Article).where(Article.url == article.url))
    assert article_result.scalar_one_or_none() is None

    run_result = await db_session.execute(select(ScrapeRun).where(ScrapeRun.id == run.id))
    stored_run = run_result.scalar_one()
    assert stored_run.source_id is None
    assert stored_run.source_name_snapshot == "Reuters"
    assert stored_run.source_slug_snapshot == "reuters"
    assert stored_run.source_category_snapshot == "general"

    second_summary = await purge_sources_by_slug(db_session, ("reuters",))
    await db_session.commit()
    assert second_summary == {
        "deleted_slugs": [],
        "sources_deleted": 0,
        "articles_deleted": 0,
        "runs_detached": 0,
    }
