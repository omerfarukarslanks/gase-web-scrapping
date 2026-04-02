from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.source import Source
from app.services.article_service import hash_url


async def create_source(
    db_session: AsyncSession,
    *,
    slug: str,
    name: str,
    category: str = "general",
    is_active: bool = True,
    has_paywall: bool = False,
    config: dict | None = None,
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
        has_paywall=has_paywall,
        config=config,
        last_scraped_at=None,
    )
    db_session.add(source)
    await db_session.flush()
    await db_session.refresh(source)
    return source


async def create_article(
    db_session: AsyncSession,
    *,
    source: Source,
    title: str,
    url: str,
    source_category: str,
    summary: str | None,
    published_at: datetime | None,
    created_at: datetime,
    category: str | None = None,
    image_url: str | None = None,
    author: str | None = None,
    content_snippet: str | None = None,
    content_text: str | None = None,
    detail_enriched: bool = False,
    detail_fetched_at: datetime | None = None,
    raw_metadata: dict | None = None,
) -> Article:
    article = Article(
        source_id=source.id,
        title=title,
        url=url,
        url_hash=hash_url(url),
        summary=summary,
        content_snippet=content_snippet,
        content_text=content_text,
        author=author,
        published_at=published_at,
        scraped_at=created_at,
        image_url=image_url,
        category=category,
        tags=["sports"] if source_category == "sports" else ["general"],
        language="en",
        source_category=source_category,
        raw_metadata=raw_metadata,
        detail_enriched=detail_enriched,
        detail_fetched_at=detail_fetched_at,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(article)
    await db_session.flush()
    await db_session.refresh(article)
    return article


@pytest.mark.asyncio
async def test_get_article_detail_returns_existing_rich_content_without_enrichment(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(db_session, slug="ap-rich", name="AP Rich")
    article = await create_article(
        db_session,
        source=source,
        title="City opens overnight cooling centers ahead of heatwave",
        url="https://ap-rich.example.com/cooling-centers",
        source_category="general",
        summary="Officials opened overnight cooling centers ahead of a fast-moving heatwave.",
        published_at=now - timedelta(minutes=12),
        created_at=now - timedelta(minutes=12),
        category="general",
        image_url="https://cdn.example.com/ap-rich-cooling.jpg",
        content_snippet="Officials opened overnight cooling centers.",
        content_text="Officials opened overnight cooling centers.\n\nResidents were advised to stay hydrated.",
        detail_enriched=True,
        detail_fetched_at=now - timedelta(minutes=5),
    )
    await db_session.commit()

    class FailingEnricher:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("Enricher should not run when detail already exists")

    monkeypatch.setattr("app.services.article_service.ArticleDetailEnricher", FailingEnricher)

    response = await client.get(f"/api/v1/articles/{article.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(article.id)
    assert payload["content_text"].startswith("Officials opened overnight cooling centers")
    assert payload["detail_enriched"] is True
    assert payload["detail_fetched_at"] is not None

    list_response = await client.get("/api/v1/articles")
    assert list_response.status_code == 200
    assert "content_text" not in list_response.json()["items"][0]


@pytest.mark.asyncio
async def test_get_article_detail_enriches_on_demand_and_persists_result(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(
        db_session,
        slug="reuters-detail",
        name="Reuters Detail",
        config={"detail_policy": "open_page_only", "respect_robots": True},
    )
    article = await create_article(
        db_session,
        source=source,
        title="Port delays disrupt regional trade flows",
        url="https://reuters-detail.example.com/port-delays",
        source_category="general",
        summary=None,
        published_at=now - timedelta(minutes=11),
        created_at=now - timedelta(minutes=11),
        category=None,
    )
    await db_session.commit()

    class FakeEnricher:
        call_count = 0

        def __init__(self, *_args, **_kwargs):
            pass

        def needs_enrichment(self, _article, *, include_content_text=False):
            assert include_content_text is True
            return True

        def should_skip_url(self, _url):
            return False

        async def is_allowed(self, _url):
            return True

        async def enrich_article(self, article_dict):
            FakeEnricher.call_count += 1
            enriched = dict(article_dict)
            enriched["summary"] = "Port delays disrupted trade flows and slowed cargo handling across the region."
            enriched["content_snippet"] = "Port delays disrupted trade flows across the region."
            enriched["content_text"] = (
                "Port delays disrupted trade flows across the region.\n\n"
                "Shipping companies said cargo handling slowed after staffing shortages worsened."
            )
            enriched["author"] = "Mina Reporter"
            enriched["image_url"] = "https://cdn.example.com/reuters-detail-port.jpg"
            enriched["category"] = "business"
            return enriched, True

    monkeypatch.setattr("app.services.article_service.ArticleDetailEnricher", FakeEnricher)

    first_response = await client.get(f"/api/v1/articles/{article.id}")
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["content_text"] is not None
    assert first_payload["detail_enriched"] is True
    assert first_payload["author"] == "Mina Reporter"
    assert first_payload["detail_fetched_at"] is not None

    second_response = await client.get(f"/api/v1/articles/{article.id}")
    assert second_response.status_code == 200
    assert FakeEnricher.call_count == 1

    refreshed = await db_session.execute(select(Article).where(Article.id == article.id))
    stored = refreshed.scalar_one()
    assert stored.content_text is not None
    assert stored.detail_enriched is True
    assert stored.detail_fetched_at is not None


@pytest.mark.asyncio
async def test_get_article_detail_skips_paywalled_source_without_fetching(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(
        db_session,
        slug="ft-detail",
        name="FT Detail",
        has_paywall=True,
        config={"detail_policy": "open_page_only"},
    )
    article = await create_article(
        db_session,
        source=source,
        title="Maritime body urges support for trapped seafarers",
        url="https://ft.example.com/content/demo-story",
        source_category="finance",
        summary="The head of the UN maritime body urged nations to support trapped seafarers.",
        published_at=now - timedelta(minutes=15),
        created_at=now - timedelta(minutes=15),
        category="business",
    )
    await db_session.commit()

    class FailingEnricher:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("Paywalled sources should not instantiate the enricher")

    monkeypatch.setattr("app.services.article_service.ArticleDetailEnricher", FailingEnricher)

    response = await client.get(f"/api/v1/articles/{article.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["content_text"] is None
    assert payload["detail_enriched"] is False


@pytest.mark.asyncio
async def test_get_article_detail_handles_fetch_failure_without_error_and_does_not_retry(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(
        db_session,
        slug="guardian-failure",
        name="Guardian Failure",
        config={"detail_policy": "open_page_only", "respect_robots": True},
    )
    article = await create_article(
        db_session,
        source=source,
        title="Ceasefire talks resume after overnight strikes",
        url="https://guardian-failure.example.com/ceasefire-talks",
        source_category="general",
        summary="Negotiators resumed talks after overnight strikes raised pressure on both sides.",
        published_at=now - timedelta(minutes=18),
        created_at=now - timedelta(minutes=18),
        category="world",
    )
    await db_session.commit()

    class FailingEnricher:
        call_count = 0

        def __init__(self, *_args, **_kwargs):
            pass

        def needs_enrichment(self, _article, *, include_content_text=False):
            assert include_content_text is True
            return True

        def should_skip_url(self, _url):
            return False

        async def is_allowed(self, _url):
            return True

        async def enrich_article(self, _article_dict):
            FailingEnricher.call_count += 1
            raise RuntimeError("detail fetch failed")

    monkeypatch.setattr("app.services.article_service.ArticleDetailEnricher", FailingEnricher)

    first_response = await client.get(f"/api/v1/articles/{article.id}")
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["content_text"] is None
    assert first_payload["detail_enriched"] is False
    assert first_payload["detail_fetched_at"] is not None

    second_response = await client.get(f"/api/v1/articles/{article.id}")
    assert second_response.status_code == 200
    assert FailingEnricher.call_count == 1

    refreshed = await db_session.execute(select(Article).where(Article.id == article.id))
    stored = refreshed.scalar_one()
    assert stored.detail_fetched_at is not None
    assert stored.raw_metadata["detail_enrichment"]["status"] == "failed"


@pytest.mark.asyncio
async def test_get_article_detail_respects_robots_block_without_error(
    client,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(
        db_session,
        slug="bbc-robots",
        name="BBC Robots",
        config={"detail_policy": "open_page_only", "respect_robots": True},
    )
    article = await create_article(
        db_session,
        source=source,
        title="Space capsule reaches orbit",
        url="https://bbc-robots.example.com/space-capsule",
        source_category="general",
        summary=None,
        published_at=now - timedelta(minutes=9),
        created_at=now - timedelta(minutes=9),
        category="science",
    )
    await db_session.commit()

    class BlockedEnricher:
        def __init__(self, *_args, **_kwargs):
            pass

        def needs_enrichment(self, _article, *, include_content_text=False):
            assert include_content_text is True
            return True

        def should_skip_url(self, _url):
            return False

        async def is_allowed(self, _url):
            return False

        async def enrich_article(self, _article_dict):
            raise AssertionError("Enrichment fetch should not run when robots block access")

    monkeypatch.setattr("app.services.article_service.ArticleDetailEnricher", BlockedEnricher)

    response = await client.get(f"/api/v1/articles/{article.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["content_text"] is None
    assert payload["detail_enriched"] is False
    assert payload["detail_fetched_at"] is not None


@pytest.mark.asyncio
async def test_articles_endpoints_hide_inactive_sources(
    client,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    active_source = await create_source(db_session, slug="active-source", name="Active Source", is_active=True)
    inactive_source = await create_source(db_session, slug="inactive-source", name="Inactive Source", is_active=False)

    visible_article = await create_article(
        db_session,
        source=active_source,
        title="Visible article",
        url="https://active-source.example.com/visible-article",
        source_category="general",
        summary="Visible article summary",
        published_at=now - timedelta(minutes=5),
        created_at=now - timedelta(minutes=5),
        category="general",
    )
    hidden_article = await create_article(
        db_session,
        source=inactive_source,
        title="Hidden article",
        url="https://inactive-source.example.com/hidden-article",
        source_category="general",
        summary="Hidden article summary",
        published_at=now - timedelta(minutes=4),
        created_at=now - timedelta(minutes=4),
        category="general",
    )
    await db_session.commit()

    list_response = await client.get("/api/v1/articles")
    assert list_response.status_code == 200
    item_ids = {item["id"] for item in list_response.json()["items"]}
    assert str(visible_article.id) in item_ids
    assert str(hidden_article.id) not in item_ids

    detail_response = await client.get(f"/api/v1/articles/{hidden_article.id}")
    assert detail_response.status_code == 404


@pytest.mark.asyncio
async def test_articles_endpoints_hide_live_urls_that_cannot_support_detail(
    client,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source = await create_source(
        db_session,
        slug="ap-live",
        name="AP Live",
        config={"detail_policy": "open_page_only", "skip_detail_url_substrings": ["/live/"]},
    )
    live_article = await create_article(
        db_session,
        source=source,
        title="Live coverage: major hearing",
        url="https://ap-live.example.com/live/major-hearing",
        source_category="general",
        summary="Live updates",
        published_at=now - timedelta(minutes=3),
        created_at=now - timedelta(minutes=3),
        category="general",
    )
    normal_article = await create_article(
        db_session,
        source=source,
        title="Standard report: major hearing",
        url="https://ap-live.example.com/major-hearing-report",
        source_category="general",
        summary="Standard report summary",
        published_at=now - timedelta(minutes=2),
        created_at=now - timedelta(minutes=2),
        category="general",
    )
    await db_session.commit()

    list_response = await client.get("/api/v1/articles")
    assert list_response.status_code == 200
    item_ids = {item["id"] for item in list_response.json()["items"]}
    assert str(normal_article.id) in item_ids
    assert str(live_article.id) not in item_ids

    detail_response = await client.get(f"/api/v1/articles/{live_article.id}")
    assert detail_response.status_code == 404
