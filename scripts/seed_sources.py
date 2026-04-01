"""Seed script to populate initial news source configurations."""
import asyncio

from sqlalchemy import select

from app.config import settings
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.models.source import Source

SOURCES = [
    # === General News ===
    {
        "name": "Reuters",
        "slug": "reuters",
        "base_url": "https://www.reuters.com",
        "rss_feeds": [
            "https://www.reuters.com/rssFeed/worldNews",
            "https://www.reuters.com/rssFeed/businessNews",
            "https://www.reuters.com/rssFeed/technologyNews",
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "AP News",
        "slug": "apnews",
        "base_url": "https://apnews.com",
        "rss_feeds": [
            "https://rsshub.app/apnews/topics/apf-topnews",
            "https://rsshub.app/apnews/topics/apf-WorldNews",
            "https://rsshub.app/apnews/topics/apf-business",
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "AFP",
        "slug": "afp",
        "base_url": "https://www.afp.com",
        "rss_feeds": [
            "https://www.afp.com/en/feed",
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "BBC News",
        "slug": "bbc",
        "base_url": "https://www.bbc.com/news",
        "rss_feeds": [
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/business/rss.xml",
            "https://feeds.bbci.co.uk/news/technology/rss.xml",
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "Al Jazeera",
        "slug": "aljazeera",
        "base_url": "https://www.aljazeera.com",
        "rss_feeds": [
            "https://www.aljazeera.com/xml/rss/all.xml",
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "The Guardian",
        "slug": "guardian",
        "base_url": "https://www.theguardian.com",
        "rss_feeds": [
            "https://www.theguardian.com/world/rss",
            "https://www.theguardian.com/uk/rss",
            "https://www.theguardian.com/business/rss",
            "https://www.theguardian.com/technology/rss",
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "ABC News",
        "slug": "abcnews",
        "base_url": "https://abcnews.go.com",
        "rss_feeds": [
            "https://abcnews.go.com/abcnews/topstories",
            "https://abcnews.go.com/abcnews/internationalheadlines",
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "CBS News",
        "slug": "cbsnews",
        "base_url": "https://www.cbsnews.com",
        "rss_feeds": [
            "https://www.cbsnews.com/latest/rss/main",
            "https://www.cbsnews.com/latest/rss/world",
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "PBS NewsHour",
        "slug": "pbs",
        "base_url": "https://www.pbs.org/newshour",
        "rss_feeds": [
            "https://www.pbs.org/newshour/feeds/rss/headlines",
            "https://www.pbs.org/newshour/feeds/rss/world",
        ],
        "category": "general",
        "has_paywall": False,
    },
    # === Finance & Economy ===
    {
        "name": "Bloomberg",
        "slug": "bloomberg",
        "base_url": "https://www.bloomberg.com",
        "rss_feeds": [
            "https://feeds.bloomberg.com/markets/news.rss",
            "https://feeds.bloomberg.com/politics/news.rss",
            "https://feeds.bloomberg.com/technology/news.rss",
        ],
        "category": "finance",
        "has_paywall": True,
    },
    {
        "name": "Financial Times",
        "slug": "ft",
        "base_url": "https://www.ft.com",
        "rss_feeds": [
            "https://www.ft.com/rss/home",
            "https://www.ft.com/rss/world",
            "https://www.ft.com/rss/companies",
        ],
        "category": "finance",
        "has_paywall": True,
    },
    {
        "name": "Wall Street Journal",
        "slug": "wsj",
        "base_url": "https://www.wsj.com",
        "rss_feeds": [
            "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
            "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
            "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        ],
        "category": "finance",
        "has_paywall": True,
    },
    {
        "name": "The Economist",
        "slug": "economist",
        "base_url": "https://www.economist.com",
        "rss_feeds": [
            "https://www.economist.com/latest/rss.xml",
            "https://www.economist.com/finance-and-economics/rss.xml",
            "https://www.economist.com/business/rss.xml",
        ],
        "category": "finance",
        "has_paywall": True,
    },
]


async def seed():
    async with async_session_factory() as session:
        for source_data in SOURCES:
            existing = await session.execute(
                select(Source).where(Source.slug == source_data["slug"])
            )
            if existing.scalar_one_or_none():
                print(f"  Skipping {source_data['slug']} (already exists)")
                continue

            source = Source(
                scraper_type="rss",
                scrape_interval_minutes=60,
                rate_limit_rpm=10,
                is_active=True,
                **source_data,
            )
            session.add(source)
            print(f"  Added {source_data['name']}")

        await session.commit()
        print("Seed completed!")


if __name__ == "__main__":
    asyncio.run(seed())
