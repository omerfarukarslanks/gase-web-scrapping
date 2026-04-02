from __future__ import annotations

from datetime import UTC, datetime
import logging
from urllib.parse import urlparse

import httpx
import trafilatura

from app.config import settings
from app.scrapers.article_metadata import ArticleMetadataExtractor
from app.scrapers.utils.rate_limiter import rate_limiter
from app.scrapers.utils.robots_txt import is_allowed as robots_allowed

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ArticleDetailEnricher:
    def __init__(self, source, metadata_extractor: ArticleMetadataExtractor | None = None):
        self.source = source
        self.metadata_extractor = metadata_extractor or ArticleMetadataExtractor()

    async def enrich_articles(self, articles: list[dict]) -> tuple[list[dict], int, int]:
        enriched_count = 0
        metadata_only_count = 0
        enriched_articles: list[dict] = []
        max_detail_enrichment_articles = int(
            (self.source.config or {}).get("max_detail_enrichment_articles", 0) or 0
        )
        enrichment_attempts = 0

        for article in articles:
            if not self._needs_enrichment(article):
                metadata_only_count += 1
                enriched_articles.append(article)
                continue

            if max_detail_enrichment_articles > 0 and enrichment_attempts >= max_detail_enrichment_articles:
                metadata_only_count += 1
                enriched_articles.append(article)
                continue

            if not await self._is_allowed(article["url"]):
                metadata_only_count += 1
                enriched_articles.append(article)
                continue

            try:
                enrichment_attempts += 1
                enriched, changed = await self._enrich_article(article)
            except Exception as exc:  # pragma: no cover - defensive logging path
                logger.warning("detail enrichment failed for %s: %s", article.get("url"), exc)
                enriched_articles.append(article)
                metadata_only_count += 1
                continue

            enriched_articles.append(enriched)
            if changed:
                enriched_count += 1
            else:
                metadata_only_count += 1

        return enriched_articles, enriched_count, metadata_only_count

    def needs_enrichment(
        self,
        article: dict,
        *,
        include_content_text: bool = False,
    ) -> bool:
        return self._needs_enrichment(article, include_content_text=include_content_text)

    def should_skip_url(self, url: str | None) -> bool:
        return self._should_skip_url(url)

    async def is_allowed(self, target_url: str) -> bool:
        return await self._is_allowed(target_url)

    async def enrich_article(self, article: dict) -> tuple[dict, bool]:
        return await self._enrich_article(article)

    async def _enrich_article(self, article: dict) -> tuple[dict, bool]:
        domain = urlparse(article["url"]).netloc
        await rate_limiter.acquire(domain, self.source.rate_limit_rpm)
        async with httpx.AsyncClient(
            timeout=min(settings.VISUAL_ASSET_FETCH_TIMEOUT_SECONDS, 8.0),
            headers={"User-Agent": settings.USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = await client.get(article["url"])
            response.raise_for_status()
            html = response.text

        extracted = self.metadata_extractor.extract_article_metadata(html, article["url"])
        trafilatura_text = trafilatura.extract(
            html,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        content_text = (trafilatura_text or "").strip() or None
        content_snippet = (content_text or "")[:1000] or None
        summary = article.get("summary") or extracted.get("summary")
        if not summary and content_snippet:
            summary = content_snippet[:280]

        enriched = dict(article)
        changed = False
        fields = {
            "title": extracted.get("title"),
            "summary": summary,
            "content_snippet": article.get("content_snippet") or content_snippet,
            "content_text": article.get("content_text") or content_text,
            "author": extracted.get("author"),
            "published_at": extracted.get("published_at"),
            "image_url": extracted.get("image_url"),
            "category": extracted.get("category"),
            "tags": extracted.get("tags"),
        }

        for key, value in fields.items():
            if value in (None, "", [], {}):
                continue
            if enriched.get(key) in (None, "", [], {}):
                enriched[key] = value
                changed = True

        raw_metadata = dict(enriched.get("raw_metadata") or {})
        raw_metadata["detail_enriched"] = changed
        raw_metadata["detail_enrichment"] = {
            "status": "success",
            "changed": changed,
            "fetched_at": utcnow().isoformat(),
            "content_length": len(content_text or ""),
        }
        enriched["raw_metadata"] = raw_metadata
        return enriched, changed

    def _needs_enrichment(self, article: dict, *, include_content_text: bool = False) -> bool:
        if self.source.has_paywall:
            return False
        detail_policy = (self.source.config or {}).get("detail_policy", "open_page_only")
        if detail_policy != "open_page_only":
            return False
        if self._should_skip_url(article.get("url")):
            return False
        missing_fields = any(
            article.get(field) in (None, "", [], {})
            for field in ("summary", "image_url", "author", "published_at", "category")
        )
        if include_content_text and article.get("content_text") in (None, "", [], {}):
            return True
        return missing_fields

    def _should_skip_url(self, url: str | None) -> bool:
        if not url:
            return True

        lowered = url.lower()
        default_skip_parts = (
            "/video/",
            "/videos/",
            "/audio/",
            "/podcast/",
            "/live/",
        )
        config_skip_parts = tuple(
            str(part).lower()
            for part in ((self.source.config or {}).get("skip_detail_url_substrings") or [])
            if part
        )
        return any(part in lowered for part in (*default_skip_parts, *config_skip_parts))

    async def _is_allowed(self, target_url: str) -> bool:
        if not (self.source.config or {}).get("respect_robots", True):
            return True
        return await robots_allowed(target_url)
