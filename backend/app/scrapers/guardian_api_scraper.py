from __future__ import annotations

import os

from bs4 import BeautifulSoup
import httpx

from app.config import settings
from app.scrapers.base import BaseNewsScraper, ScrapedArticle
from app.scrapers.discovery_utils import parse_datetime_to_utc_naive
from app.scrapers.utils.rate_limiter import rate_limiter


class GuardianApiScraper(BaseNewsScraper):
    async def fetch_articles(self) -> list[dict]:
        config = self.source.config or {}
        api_base_url = config.get("api_base_url") or "https://content.guardianapis.com"
        api_key_env = config.get("api_key_env") or "GUARDIAN_API_KEY"
        api_key = os.getenv(api_key_env) or getattr(settings, api_key_env, None)
        if not api_key:
            raise RuntimeError(f"Missing Guardian API key in {api_key_env}")

        api_sections = config.get("api_sections") or [{"section": "world", "category": "world"}]
        page_size = int(config.get("api_page_size", 20))
        articles: list[dict] = []

        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": settings.USER_AGENT},
            follow_redirects=True,
        ) as client:
            for section_entry in api_sections:
                await rate_limiter.acquire(httpx.URL(api_base_url).host or "", self.source.rate_limit_rpm)
                section = section_entry.get("section")
                category = section_entry.get("category")
                params = {
                    "api-key": api_key,
                    "section": section,
                    "page-size": page_size,
                    "order-by": "newest",
                    "show-fields": "trailText,thumbnail,byline,bodyText",
                }
                if self.source.last_scraped_at:
                    params["from-date"] = self.source.last_scraped_at.date().isoformat()

                response = await client.get(f"{api_base_url}/search", params=params)
                response.raise_for_status()
                payload = response.json()
                results = payload.get("response", {}).get("results", [])

                for result in results:
                    fields = result.get("fields") or {}
                    summary_html = fields.get("trailText")
                    summary = None
                    if summary_html:
                        summary = BeautifulSoup(summary_html, "lxml").get_text(" ", strip=True)

                    article = ScrapedArticle(
                        title=result.get("webTitle", "").strip(),
                        url=result.get("webUrl", "").strip(),
                        summary=summary,
                        content_snippet=(fields.get("bodyText") or "")[:1000] or None,
                        author=fields.get("byline"),
                        published_at=parse_datetime_to_utc_naive(result.get("webPublicationDate")),
                        image_url=fields.get("thumbnail"),
                        category=category or result.get("sectionId"),
                        tags=[tag.get("webTitle") for tag in result.get("tags", []) if tag.get("webTitle")] or None,
                        raw_metadata={"discovery_method": "api"},
                    )
                    if article.title and article.url:
                        articles.append(article.to_dict())

        return articles
