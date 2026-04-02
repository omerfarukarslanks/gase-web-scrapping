import logging
from datetime import datetime, timezone

import feedparser
import httpx
from dateutil import parser as dateparser

from app.config import settings
from app.scrapers.base import BaseNewsScraper, ScrapedArticle

logger = logging.getLogger(__name__)


class RSSNewsScraper(BaseNewsScraper):
    """Generic RSS/Atom feed scraper. Source-specific scrapers subclass this."""

    def get_feeds(self) -> list[dict]:
        """Return list of feed dicts: [{"url": "...", "category": "..."}].

        Supports both legacy (flat string list) and new (dict list) formats.
        """
        feeds = self.source.rss_feeds or []
        result = []
        for feed in feeds:
            if isinstance(feed, str):
                result.append({"url": feed, "category": None})
            elif isinstance(feed, dict):
                result.append({
                    "url": feed.get("url", ""),
                    "category": feed.get("category"),
                })
        return result

    def parse_category(self, entry) -> str | None:
        """Extract category from feed entry tags. Override for source-specific logic."""
        if hasattr(entry, "tags") and entry.tags:
            return entry.tags[0].get("term", None)
        return None

    def parse_author(self, entry) -> str | None:
        """Extract author from feed entry."""
        if hasattr(entry, "author"):
            return entry.author
        if hasattr(entry, "authors") and entry.authors:
            return entry.authors[0].get("name", None)
        return None

    def parse_image(self, entry) -> str | None:
        """Extract image URL from feed entry."""
        # Check media:content
        if hasattr(entry, "media_content") and entry.media_content:
            return entry.media_content[0].get("url", None)
        # Check media:thumbnail
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            return entry.media_thumbnail[0].get("url", None)
        # Check enclosures
        if hasattr(entry, "enclosures") and entry.enclosures:
            for enc in entry.enclosures:
                if enc.get("type", "").startswith("image/"):
                    return enc.get("href") or enc.get("url")
        return None

    def parse_published_at(self, entry) -> datetime | None:
        """Parse publication date from feed entry.

        Always returns a timezone-naive UTC datetime to match the DB column
        (TIMESTAMP WITHOUT TIME ZONE).
        """
        date_str = getattr(entry, "published", None) or getattr(entry, "updated", None)
        if date_str:
            try:
                dt = dateparser.parse(date_str)
                if dt is None:
                    return None
                # Convert to UTC then strip tzinfo so asyncpg gets a naive datetime
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except (ValueError, TypeError):
                pass
        return None

    def parse_summary(self, entry) -> str | None:
        """Extract summary/description from feed entry."""
        summary = getattr(entry, "summary", None) or getattr(entry, "description", None)
        if summary:
            # Strip HTML tags for clean text
            from bs4 import BeautifulSoup
            return BeautifulSoup(summary, "lxml").get_text(strip=True)[:1000]
        return None

    def parse_entry(self, entry, feed_category: str | None = None) -> ScrapedArticle | None:
        """Parse a single feed entry into a ScrapedArticle.

        feed_category: RSS entry'nin kendi tag'i yoksa bu deger kullanilir.
        """
        title = getattr(entry, "title", None)
        link = getattr(entry, "link", None)

        if not title or not link:
            return None

        # RSS entry tag'i oncelikli, yoksa feed'in kendi kategorisi
        category = self.parse_category(entry) or feed_category

        return ScrapedArticle(
            title=title.strip(),
            url=link.strip(),
            summary=self.parse_summary(entry),
            author=self.parse_author(entry),
            published_at=self.parse_published_at(entry),
            image_url=self.parse_image(entry),
            category=category,
            tags=self._extract_tags(entry),
        )

    def _extract_tags(self, entry) -> list[str] | None:
        if hasattr(entry, "tags") and entry.tags:
            return [t.get("term", "") for t in entry.tags if t.get("term")]
        return None

    async def fetch_feed(self, feed_url: str, feed_category: str | None = None) -> list[ScrapedArticle]:
        """Fetch and parse a single RSS feed."""
        articles = []
        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers={"User-Agent": settings.USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = await client.get(feed_url)
                response.raise_for_status()

            feed = feedparser.parse(response.text)

            for entry in feed.entries:
                article = self.parse_entry(entry, feed_category)
                if article:
                    articles.append(article)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {feed_url}: {e}")
        except Exception as e:
            logger.error(f"Error parsing feed {feed_url}: {e}")

        return articles

    async def fetch_articles(self) -> list[dict]:
        """Fetch articles from all configured RSS feeds."""
        all_articles = []
        seen_urls = set()

        for feed in self.get_feeds():
            feed_url = feed["url"]
            feed_category = feed.get("category")

            if not feed_url:
                continue

            logger.info(f"Fetching feed: {feed_url} (category={feed_category})")
            articles = await self.fetch_feed(feed_url, feed_category)

            for article in articles:
                if article.url not in seen_urls:
                    seen_urls.add(article.url)
                    all_articles.append(article.to_dict())

        logger.info(f"{self.source_name}: fetched {len(all_articles)} unique articles")
        return all_articles
