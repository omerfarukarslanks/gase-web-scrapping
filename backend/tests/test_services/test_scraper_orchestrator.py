from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.models.article import Article
from app.models.source import Source
from app.services.article_service import hash_url
from app.services.scraper_orchestrator import scrape_source


@pytest.mark.asyncio
async def test_scrape_source_records_discovery_stats(db_session, monkeypatch):
    source = Source(
        name="Guardian",
        slug="guardian",
        base_url="https://www.theguardian.com",
        rss_feeds=[],
        scraper_type="api",
        category="general",
        is_active=True,
        scrape_interval_minutes=60,
        rate_limit_rpm=10,
        has_paywall=False,
        config={"discovery_priority": ["api", "rss"], "detail_policy": "open_page_only"},
    )
    db_session.add(source)
    await db_session.flush()

    class FakeScraper:
        last_fetch_stats = {
            "discovery_method_used": "api",
            "detail_enriched_count": 1,
            "metadata_only_count": 0,
        }

        async def fetch_articles(self):
            return [
                {
                    "title": "Guardian story",
                    "url": "https://www.theguardian.com/world/2026/apr/02/story",
                    "summary": "Summary",
                    "published_at": datetime.utcnow(),
                }
            ]

    monkeypatch.setattr(
        "app.services.scraper_orchestrator.get_scraper",
        lambda _source: FakeScraper(),
    )

    run = await scrape_source(db_session, source)

    assert run.status == "completed"
    assert run.discovery_method_used == "api"
    assert run.detail_enriched_count == 1
    assert run.metadata_only_count == 0
    assert run.source_name_snapshot == "Guardian"
    assert run.source_slug_snapshot == "guardian"
    assert run.source_category_snapshot == "general"

    article_count = await db_session.scalar(
        select(func.count()).select_from(Article).where(Article.source_id == source.id)
    )
    assert article_count == 1


@pytest.mark.asyncio
async def test_scrape_source_skips_existing_articles_in_batch(db_session, monkeypatch):
    source = Source(
        name="France 24",
        slug="france24",
        base_url="https://www.france24.com",
        rss_feeds=[],
        scraper_type="rss",
        category="general",
        is_active=True,
        scrape_interval_minutes=60,
        rate_limit_rpm=10,
        has_paywall=False,
        config={"discovery_priority": ["rss"]},
    )
    db_session.add(source)
    await db_session.flush()

    db_session.add(
        Article(
            source_id=source.id,
            title="Existing story",
            url="https://www.france24.com/en/world/2026/04/02/existing-story",
            url_hash=hash_url("https://www.france24.com/en/world/2026/04/02/existing-story"),
            published_at=datetime.utcnow(),
            scraped_at=datetime.utcnow(),
        )
    )
    await db_session.flush()

    class FakeScraper:
        last_fetch_stats = {
            "discovery_method_used": "rss",
            "detail_enriched_count": 0,
            "metadata_only_count": 2,
        }

        async def fetch_articles(self):
            return [
                {
                    "title": "Existing story",
                    "url": "https://www.france24.com/en/world/2026/04/02/existing-story",
                    "summary": "Already saved",
                    "published_at": datetime.utcnow(),
                },
                {
                    "title": "Brand new story",
                    "url": "https://www.france24.com/en/world/2026/04/02/brand-new-story",
                    "summary": "Fresh",
                    "published_at": datetime.utcnow(),
                },
            ]

    monkeypatch.setattr(
        "app.services.scraper_orchestrator.get_scraper",
        lambda _source: FakeScraper(),
    )

    run = await scrape_source(db_session, source)

    assert run.status == "completed"
    assert run.articles_found == 2
    assert run.articles_new == 1

    article_count = await db_session.scalar(
        select(func.count()).select_from(Article).where(Article.source_id == source.id)
    )
    assert article_count == 2
