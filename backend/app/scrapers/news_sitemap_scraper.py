from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

import httpx

from app.config import settings
from app.scrapers.base import BaseNewsScraper, ScrapedArticle
from app.scrapers.discovery_utils import dedupe_articles, parse_datetime_to_utc_naive
from app.scrapers.utils.rate_limiter import rate_limiter
from app.scrapers.utils.robots_txt import is_allowed as robots_allowed

logger = logging.getLogger(__name__)


class NewsSitemapScraper(BaseNewsScraper):
    async def fetch_articles(self) -> list[dict]:
        config = self.source.config or {}
        sitemap_urls = config.get("sitemap_urls") or []
        if not sitemap_urls:
            return []

        articles: list[dict] = []
        seen_sitemaps: set[str] = set()

        for sitemap_url in sitemap_urls:
            articles.extend(await self._fetch_sitemap_recursive(sitemap_url, seen_sitemaps))

        deduped = dedupe_articles(articles)
        for article in deduped:
            raw_metadata = dict(article.get("raw_metadata") or {})
            raw_metadata.setdefault("discovery_method", "news_sitemap")
            article["raw_metadata"] = raw_metadata
        return deduped

    async def _fetch_sitemap_recursive(self, sitemap_url: str, seen_sitemaps: set[str]) -> list[dict]:
        if sitemap_url in seen_sitemaps:
            return []
        seen_sitemaps.add(sitemap_url)
        if (self.source.config or {}).get("respect_robots", True) and not await robots_allowed(sitemap_url):
            return []

        try:
            await rate_limiter.acquire(httpx.URL(sitemap_url).host or "", self.source.rate_limit_rpm)
            async with httpx.AsyncClient(
                timeout=15,
                headers={"User-Agent": settings.USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = await client.get(sitemap_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("%s sitemap fetch failed: %s", sitemap_url, exc)
            return []

        root = ET.fromstring(response.text)
        root_name = self._strip_namespace(root.tag)

        if root_name == "sitemapindex":
            articles: list[dict] = []
            child_urls: list[str] = []
            for child in root.findall("{*}sitemap"):
                loc_node = child.find("{*}loc")
                if loc_node is None or not loc_node.text:
                    continue
                child_urls.append(loc_node.text.strip())

            max_nested = int((self.source.config or {}).get("max_nested_sitemaps", 10))
            prioritized = sorted(
                child_urls,
                key=lambda value: (
                    "news" not in value.lower(),
                    "latest" not in value.lower(),
                ),
            )[:max_nested]

            for child_url in prioritized:
                articles.extend(await self._fetch_sitemap_recursive(child_url, seen_sitemaps))
            return articles

        if root_name != "urlset":
            return []

        return self.parse_sitemap_document(response.text)

    def parse_sitemap_document(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        articles: list[dict] = []
        max_urls = int((self.source.config or {}).get("max_urls_per_sitemap", 100))

        for url_node in root.findall("{*}url")[:max_urls]:
            loc = self._find_text(url_node, "loc")
            if not loc:
                continue

            title = self._find_text(url_node, "title") or self._title_from_url(loc)
            publication_date = self._find_text(url_node, "publication_date") or self._find_text(url_node, "lastmod")
            keywords = self._find_text(url_node, "keywords")
            category = self._find_text(url_node, "section")

            article = ScrapedArticle(
                title=title,
                url=loc,
                published_at=parse_datetime_to_utc_naive(publication_date),
                category=category,
                tags=[part.strip() for part in keywords.split(",") if part.strip()] if keywords else None,
                raw_metadata={"discovery_method": "news_sitemap"},
            )
            articles.append(article.to_dict())

        return articles

    def _find_text(self, node: ET.Element, tag_name: str) -> str | None:
        for child in node.iter():
            if self._strip_namespace(child.tag) == tag_name and child.text:
                return child.text.strip()
        return None

    def _strip_namespace(self, tag: str) -> str:
        return tag.split("}", 1)[-1].split(":", 1)[-1]

    def _title_from_url(self, url: str) -> str:
        slug = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").strip()
        return slug[:160] or url
