from __future__ import annotations

import logging

from app.scrapers.article_detail import ArticleDetailEnricher
from app.scrapers.discovery_utils import dedupe_articles
from app.scrapers.guardian_api_scraper import GuardianApiScraper
from app.scrapers.news_sitemap_scraper import NewsSitemapScraper
from app.scrapers.section_listing_scraper import SectionListingScraper

logger = logging.getLogger(__name__)


class ConfigurableNewsScraper:
    def __init__(self, source, rss_scraper_factory):
        self.source = source
        self.source_slug = source.slug
        self.source_name = source.name
        self._rss_scraper_factory = rss_scraper_factory
        self.last_fetch_stats = {
            "discovery_method_used": None,
            "detail_enriched_count": 0,
            "metadata_only_count": 0,
        }

    async def fetch_articles(self) -> list[dict]:
        config = self.source.config or {}
        methods = self._get_discovery_priority(config)
        combine_methods = bool(config.get("combine_discovery_methods", False))

        all_articles: list[dict] = []
        first_successful_method: str | None = None

        for method in methods:
            scraper = self._build_scraper(method)
            if scraper is None:
                continue

            try:
                articles = await scraper.fetch_articles()
            except Exception as exc:
                logger.warning("%s discovery method %s failed: %s", self.source.slug, method, exc)
                continue

            if not articles:
                continue

            if first_successful_method is None:
                first_successful_method = method

            for article in articles:
                raw_metadata = dict(article.get("raw_metadata") or {})
                raw_metadata.setdefault("discovery_method", method)
                article["raw_metadata"] = raw_metadata
            all_articles.extend(articles)

            if not combine_methods:
                break

        deduped = dedupe_articles(all_articles)

        detail_enriched_count = 0
        metadata_only_count = len(deduped)
        if config.get("detail_policy", "open_page_only") == "open_page_only" and not self.source.has_paywall:
            enricher = ArticleDetailEnricher(self.source)
            deduped, detail_enriched_count, metadata_only_count = await enricher.enrich_articles(deduped)

        self.last_fetch_stats = {
            "discovery_method_used": first_successful_method,
            "detail_enriched_count": detail_enriched_count,
            "metadata_only_count": metadata_only_count,
        }
        return deduped

    def _get_discovery_priority(self, config: dict) -> list[str]:
        priority = config.get("discovery_priority")
        if priority:
            return list(dict.fromkeys(priority))
        return list(dict.fromkeys([self.source.scraper_type, "rss"]))

    def _build_scraper(self, method: str):
        if method == "api" and self.source.slug == "guardian":
            return GuardianApiScraper(self.source)
        if method == "news_sitemap":
            return NewsSitemapScraper(self.source)
        if method == "section_html":
            return SectionListingScraper(self.source)
        if method == "rss":
            return self._rss_scraper_factory(self.source)
        return None
