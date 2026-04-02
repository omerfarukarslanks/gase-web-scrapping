from types import SimpleNamespace
import warnings

import pytest
from bs4 import MarkupResemblesLocatorWarning

from app.scrapers.article_detail import ArticleDetailEnricher
from app.scrapers.article_metadata import ArticleMetadataExtractor
from app.scrapers.configurable_scraper import ConfigurableNewsScraper
from app.scrapers.news_sitemap_scraper import NewsSitemapScraper
from app.scrapers.rss_scraper import RSSNewsScraper


def build_source(**overrides):
    base = {
        "slug": "demo",
        "name": "Demo Source",
        "scraper_type": "news_sitemap",
        "config": {},
        "has_paywall": False,
        "last_scraped_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_rss_parse_summary_skips_html_parser_for_plain_text_locator():
    source = build_source(rss_feeds=["https://example.com/feed.xml"])
    scraper = RSSNewsScraper(source)
    entry = SimpleNamespace(summary="https://abcnews.com/video/41463246")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        summary = scraper.parse_summary(entry)

    assert summary == "https://abcnews.com/video/41463246"
    assert not any(issubclass(w.category, MarkupResemblesLocatorWarning) for w in caught)


def test_extract_article_metadata_from_jsonld():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "Space capsule reaches orbit",
            "description": "A clean metadata summary.",
            "datePublished": "2026-04-02T08:15:00Z",
            "articleSection": "science",
            "keywords": ["space", "launch"],
            "author": {"@type": "Person", "name": "Ada Reporter"},
            "image": {"url": "https://example.com/hero.jpg"}
          }
        </script>
      </head>
    </html>
    """

    extracted = ArticleMetadataExtractor().extract_article_metadata(html, "https://example.com/story")

    assert extracted["title"] == "Space capsule reaches orbit"
    assert extracted["summary"] == "A clean metadata summary."
    assert extracted["author"] == "Ada Reporter"
    assert extracted["category"] == "science"
    assert extracted["image_url"] == "https://example.com/hero.jpg"
    assert extracted["tags"] == ["space", "launch"]
    assert extracted["published_at"] is not None


def test_extract_links_from_listing_filters_navigation():
    html = """
    <html>
      <body>
        <a href="/news/2026/04/02/space-capsule-reaches-orbit">Space capsule reaches orbit after clean launch</a>
        <a href="/tag/space">Space Tag</a>
        <a href="https://external.example.com/story">Outside story</a>
        <a href="/news/2026/04/02/space-capsule-reaches-orbit">Space capsule reaches orbit after clean launch</a>
      </body>
    </html>
    """

    links = ArticleMetadataExtractor().extract_links_from_listing(html, "https://example.com/world")

    assert links == [
        {
            "url": "https://example.com/news/2026/04/02/space-capsule-reaches-orbit",
            "title": "Space capsule reaches orbit after clean launch",
        }
    ]


def test_extract_links_from_listing_supports_stricter_filters():
    html = """
    <html>
      <body>
        <a href="/en/news-alerts-settings">Manage alerts</a>
        <a href="/en/replay/latest-news">Latest newscast</a>
        <a href="/en/world/2026/04/02/real-story">Real story from today with enough title text</a>
        <a href="/en/business-tech">Business and tech landing page headline text</a>
      </body>
    </html>
    """

    links = ArticleMetadataExtractor().extract_links_from_listing(
        html,
        "https://www.france24.com/en/world/",
        exclude_url_substrings=["/replay/", "/news-alerts"],
        require_date_path=True,
    )

    assert links == [
        {
            "url": "https://www.france24.com/en/world/2026/04/02/real-story",
            "title": "Real story from today with enough title text",
        }
    ]


def test_parse_news_sitemap_document():
    xml = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url>
        <loc>https://example.com/world/story-1</loc>
        <news:news>
          <news:publication>
            <news:name>Example News</news:name>
          </news:publication>
          <news:publication_date>2026-04-02T08:15:00Z</news:publication_date>
          <news:title>Story One</news:title>
          <news:keywords>world, politics</news:keywords>
        </news:news>
      </url>
    </urlset>
    """

    scraper = NewsSitemapScraper(build_source())
    articles = scraper.parse_sitemap_document(xml)

    assert len(articles) == 1
    assert articles[0]["title"] == "Story One"
    assert articles[0]["tags"] == ["world", "politics"]
    assert articles[0]["published_at"] is not None


@pytest.mark.asyncio
async def test_configurable_scraper_stops_after_first_successful_method(monkeypatch):
    source = build_source(
        config={
            "discovery_priority": ["api", "news_sitemap", "rss"],
            "detail_policy": "metadata_only",
        }
    )

    class FakeScraper:
        def __init__(self, articles=None, exc=None):
            self._articles = articles or []
            self._exc = exc

        async def fetch_articles(self):
            if self._exc:
                raise self._exc
            return [dict(article) for article in self._articles]

    configurable = ConfigurableNewsScraper(source, lambda _: FakeScraper())
    calls: list[str] = []

    def fake_build_scraper(method: str):
        calls.append(method)
        if method == "api":
            return FakeScraper(exc=RuntimeError("api unavailable"))
        if method == "news_sitemap":
            return FakeScraper(
                [{"title": "A", "url": "https://example.com/story-a", "summary": "one"}]
            )
        if method == "rss":
            return FakeScraper(
                [
                    {"title": "A again", "url": "https://example.com/story-a?utm_source=test"},
                    {"title": "B", "url": "https://example.com/story-b"},
                ]
            )
        return None

    monkeypatch.setattr(configurable, "_build_scraper", fake_build_scraper)
    articles = await configurable.fetch_articles()

    assert [article["url"] for article in articles] == [
        "https://example.com/story-a",
    ]
    assert calls == ["api", "news_sitemap"]
    assert configurable.last_fetch_stats["discovery_method_used"] == "news_sitemap"
    assert configurable.last_fetch_stats["metadata_only_count"] == 1


@pytest.mark.asyncio
async def test_open_page_detail_policy_uses_enricher(monkeypatch):
    source = build_source(
        config={
            "discovery_priority": ["news_sitemap"],
            "detail_policy": "open_page_only",
        }
    )

    class FakeScraper:
        async def fetch_articles(self):
            return [{"title": "A", "url": "https://example.com/story-a"}]

    configurable = ConfigurableNewsScraper(source, lambda _: FakeScraper())
    monkeypatch.setattr(configurable, "_build_scraper", lambda method: FakeScraper())

    class FakeEnricher:
        def __init__(self, *_args, **_kwargs):
            pass

        async def enrich_articles(self, articles):
            enriched = [dict(articles[0], summary="Detailed summary")]
            return enriched, 1, 0

    monkeypatch.setattr(
        "app.scrapers.configurable_scraper.ArticleDetailEnricher",
        FakeEnricher,
    )

    articles = await configurable.fetch_articles()

    assert articles[0]["summary"] == "Detailed summary"
    assert configurable.last_fetch_stats["detail_enriched_count"] == 1
    assert configurable.last_fetch_stats["metadata_only_count"] == 0


@pytest.mark.asyncio
async def test_paywalled_source_skips_detail_enrichment(monkeypatch):
    source = build_source(
        has_paywall=True,
        config={
            "discovery_priority": ["news_sitemap"],
            "detail_policy": "open_page_only",
        },
    )

    class FakeScraper:
        async def fetch_articles(self):
            return [{"title": "A", "url": "https://example.com/story-a"}]

    configurable = ConfigurableNewsScraper(source, lambda _: FakeScraper())
    monkeypatch.setattr(configurable, "_build_scraper", lambda method: FakeScraper())

    class FailingEnricher:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("Enricher should not run for paywalled sources")

    monkeypatch.setattr(
        "app.scrapers.configurable_scraper.ArticleDetailEnricher",
        FailingEnricher,
    )

    articles = await configurable.fetch_articles()

    assert len(articles) == 1
    assert configurable.last_fetch_stats["detail_enriched_count"] == 0
    assert configurable.last_fetch_stats["metadata_only_count"] == 1


def test_detail_enricher_skips_video_urls():
    source = build_source(
        config={
            "detail_policy": "open_page_only",
            "skip_detail_url_substrings": ["/video/"],
        }
    )
    enricher = ArticleDetailEnricher(source)

    assert not enricher._needs_enrichment(
        {
            "url": "https://abcnews.go.com/video/41463246",
            "summary": None,
            "image_url": None,
            "author": None,
            "published_at": None,
            "category": None,
        }
    )
