from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scrape_run import ScrapeRun
from app.models.source import Source


async def create_source(
    db_session: AsyncSession,
    *,
    slug: str,
    name: str,
    category: str = "general",
    is_active: bool = True,
) -> Source:
    source = Source(
        name=name,
        slug=slug,
        base_url=f"https://{slug}.example.com",
        rss_feeds=[],
        scraper_type="rss",
        category=category,
        is_active=is_active,
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


async def create_run(
    db_session: AsyncSession,
    *,
    source: Source | None,
    source_name_snapshot: str,
    source_slug_snapshot: str,
    source_category_snapshot: str,
    started_at: datetime,
    completed_at: datetime,
    articles_new: int,
    status: str = "completed",
) -> ScrapeRun:
    run = ScrapeRun(
        source_id=source.id if source else None,
        source_name_snapshot=source_name_snapshot,
        source_slug_snapshot=source_slug_snapshot,
        source_category_snapshot=source_category_snapshot,
        status=status,
        articles_found=articles_new,
        articles_new=articles_new,
        articles_updated=0,
        detail_enriched_count=0,
        metadata_only_count=articles_new,
        discovery_method_used="rss",
        error_message=None,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=(completed_at - started_at).total_seconds(),
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    return run


@pytest.mark.asyncio
async def test_dashboard_stats_use_scrape_history_even_without_articles(
    client,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    active_source = await create_source(
        db_session,
        slug="apnews",
        name="AP News",
        category="general",
        is_active=True,
    )
    await create_run(
        db_session,
        source=active_source,
        source_name_snapshot="AP News",
        source_slug_snapshot="apnews",
        source_category_snapshot="general",
        started_at=now - timedelta(minutes=5),
        completed_at=now - timedelta(minutes=4),
        articles_new=7,
    )
    await create_run(
        db_session,
        source=None,
        source_name_snapshot="Reuters",
        source_slug_snapshot="reuters",
        source_category_snapshot="general",
        started_at=now - timedelta(minutes=3),
        completed_at=now - timedelta(minutes=2),
        articles_new=5,
    )
    await db_session.commit()

    response = await client.get("/api/v1/scrape-runs/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["articles_today"] == 12
    assert payload["total_articles"] == 12
    assert payload["active_sources"] == 1
    assert payload["total_sources"] == 1
    assert {item["slug"] for item in payload["articles_by_source"]} == {"apnews", "reuters"}
    recent_runs = {item["source_slug"]: item for item in payload["recent_runs"]}
    assert recent_runs["reuters"]["source_name"] == "Reuters"
    assert recent_runs["reuters"]["source_id"] is None


@pytest.mark.asyncio
async def test_list_and_latest_scrape_runs_include_snapshot_fallbacks(
    client,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    await create_run(
        db_session,
        source=None,
        source_name_snapshot="Bloomberg",
        source_slug_snapshot="bloomberg",
        source_category_snapshot="finance",
        started_at=now - timedelta(minutes=6),
        completed_at=now - timedelta(minutes=5),
        articles_new=3,
    )
    await create_run(
        db_session,
        source=None,
        source_name_snapshot="Bloomberg",
        source_slug_snapshot="bloomberg",
        source_category_snapshot="finance",
        started_at=now - timedelta(minutes=3),
        completed_at=now - timedelta(minutes=2),
        articles_new=2,
    )
    await db_session.commit()

    list_response = await client.get("/api/v1/scrape-runs", params={"source_slug": "bloomberg"})
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 2
    assert all(item["source_slug"] == "bloomberg" for item in list_payload)

    latest_response = await client.get("/api/v1/scrape-runs/latest")
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()
    bloomberg_runs = [item for item in latest_payload if item["source_slug"] == "bloomberg"]
    assert len(bloomberg_runs) == 1
    assert bloomberg_runs[0]["articles_new"] == 2


@pytest.mark.asyncio
async def test_sources_endpoint_returns_only_active_sources(
    client,
    db_session: AsyncSession,
) -> None:
    await create_source(db_session, slug="active-source", name="Active Source", is_active=True)
    await create_source(db_session, slug="inactive-source", name="Inactive Source", is_active=False)
    await db_session.commit()

    list_response = await client.get("/api/v1/sources")
    assert list_response.status_code == 200
    listed_slugs = {item["slug"] for item in list_response.json()}
    assert listed_slugs == {"active-source"}

    detail_response = await client.get("/api/v1/sources/inactive-source")
    assert detail_response.status_code == 404
