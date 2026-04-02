from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.scrape_run import ScrapeRun
from app.models.source import Source
from app.services.article_service import hash_url
from app.workers.celery_app import celery_app
from app.workers.scrape_tasks import delete_articles_before, get_retention_cutoff


async def create_source(db_session: AsyncSession, *, slug: str, name: str) -> Source:
    source = Source(
        name=name,
        slug=slug,
        base_url=f"https://{slug}.example.com",
        rss_feeds=[],
        scraper_type="rss",
        category="general",
        is_active=True,
        scrape_interval_minutes=60,
        rate_limit_rpm=10,
        has_paywall=False,
        config={},
        last_scraped_at=None,
    )
    db_session.add(source)
    await db_session.flush()
    await db_session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_get_retention_cutoff_uses_istanbul_midnight_window() -> None:
    now = datetime(2026, 4, 2, 0, 0, tzinfo=ZoneInfo("Europe/Istanbul"))

    cutoff_local, cutoff_utc_naive = get_retention_cutoff(now=now)

    assert cutoff_local.isoformat() == "2026-04-01T16:00:00+03:00"
    assert cutoff_utc_naive == datetime(2026, 4, 1, 13, 0)


@pytest.mark.asyncio
async def test_delete_articles_before_only_removes_old_articles(
    db_session: AsyncSession,
) -> None:
    source = await create_source(db_session, slug="guardian", name="Guardian")
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = datetime(2026, 4, 1, 13, 0)

    old_article = Article(
        source_id=source.id,
        title="Old story",
        url="https://guardian.example.com/old-story",
        url_hash=hash_url("https://guardian.example.com/old-story"),
        summary="Old summary",
        published_at=now,
        scraped_at=now,
        source_category="general",
        created_at=datetime(2026, 4, 1, 12, 59),
    )
    fresh_article = Article(
        source_id=source.id,
        title="Fresh story",
        url="https://guardian.example.com/fresh-story",
        url_hash=hash_url("https://guardian.example.com/fresh-story"),
        summary="Fresh summary",
        published_at=now,
        scraped_at=now,
        source_category="general",
        created_at=datetime(2026, 4, 1, 13, 1),
    )
    run = ScrapeRun(
        source_id=source.id,
        source_name_snapshot="Guardian",
        source_slug_snapshot="guardian",
        source_category_snapshot="general",
        status="completed",
        articles_found=2,
        articles_new=2,
        articles_updated=0,
        detail_enriched_count=0,
        metadata_only_count=2,
        discovery_method_used="rss",
        error_message=None,
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
    )
    db_session.add_all([old_article, fresh_article, run])
    await db_session.commit()

    deleted = await delete_articles_before(db_session, cutoff)

    assert deleted == 1
    remaining_articles = await db_session.scalar(select(func.count()).select_from(Article))
    remaining_runs = await db_session.scalar(select(func.count()).select_from(ScrapeRun))
    assert remaining_articles == 1
    assert remaining_runs == 1

    remaining_article = await db_session.scalar(
        select(Article).where(Article.url == "https://guardian.example.com/fresh-story")
    )
    assert remaining_article is not None


def test_celery_schedule_uses_hourly_scrape_and_midnight_cleanup() -> None:
    schedule = celery_app.conf.beat_schedule

    assert celery_app.conf.timezone == "Europe/Istanbul"
    assert set(schedule.keys()) == {"scrape-all-sources", "cleanup-retained-articles"}

    scrape_schedule = schedule["scrape-all-sources"]["schedule"]
    cleanup_schedule = schedule["cleanup-retained-articles"]["schedule"]

    assert schedule["scrape-all-sources"]["task"] == "app.workers.scrape_tasks.scrape_all_active_sources"
    assert schedule["cleanup-retained-articles"]["task"] == "app.workers.scrape_tasks.cleanup_retained_articles"
    assert scrape_schedule.minute == {0}
    assert len(scrape_schedule.hour) == 24
    assert cleanup_schedule.minute == {0}
    assert cleanup_schedule.hour == {0}
