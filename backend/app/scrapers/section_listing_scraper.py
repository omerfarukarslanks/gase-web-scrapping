from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.scrapers.article_metadata import ArticleMetadataExtractor
from app.scrapers.base import BaseNewsScraper, ScrapedArticle
from app.scrapers.discovery_utils import dedupe_articles
from app.scrapers.utils.rate_limiter import rate_limiter
from app.scrapers.utils.robots_txt import is_allowed as robots_allowed

logger = logging.getLogger(__name__)


class SectionListingScraper(BaseNewsScraper):
    def __init__(self, source):
        super().__init__(source)
        self.metadata_extractor = ArticleMetadataExtractor()

    async def fetch_articles(self) -> list[dict]:
        config = self.source.config or {}
        section_urls = config.get("section_urls") or []
        max_links_per_section = int(config.get("max_links_per_section", 30))
        exclude_url_substrings = config.get("exclude_url_substrings") or []
        require_date_path = bool(config.get("require_date_path", False))
        articles: list[dict] = []

        for section_entry in section_urls:
            if isinstance(section_entry, str):
                section_url = section_entry
                category = None
            else:
                section_url = section_entry.get("url", "")
                category = section_entry.get("category")

            if not section_url:
                continue
            if (self.source.config or {}).get("respect_robots", True) and not await robots_allowed(section_url):
                continue

            try:
                await rate_limiter.acquire(httpx.URL(section_url).host or "", self.source.rate_limit_rpm)
                async with httpx.AsyncClient(
                    timeout=15,
                    headers={"User-Agent": settings.USER_AGENT},
                    follow_redirects=True,
                ) as client:
                    response = await client.get(section_url)
                    response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("%s section fetch failed: %s", section_url, exc)
                continue

            links = self.metadata_extractor.extract_links_from_listing(
                response.text,
                section_url,
                exclude_url_substrings=exclude_url_substrings,
                require_date_path=require_date_path,
            )[:max_links_per_section]
            for link in links:
                article = ScrapedArticle(
                    title=link["title"],
                    url=link["url"],
                    category=category,
                    raw_metadata={"discovery_method": "section_html"},
                )
                articles.append(article.to_dict())

        return dedupe_articles(articles)
