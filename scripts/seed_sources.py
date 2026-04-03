"""Seed script to populate initial news source configurations."""
import asyncio

from sqlalchemy import select

from app.config import settings
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.models.source import Source
from app.source_policy import REMOVED_SOURCE_SLUGS

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


SOURCE_DISCOVERY_OVERRIDES = {
    "reuters": {
        "is_active": False,
        "scraper_type": "rss",
        "config": {
            "section_urls": [
                {"url": "https://www.reuters.com/world/", "category": "world"},
                {"url": "https://www.reuters.com/business/", "category": "business"},
                {"url": "https://www.reuters.com/technology/", "category": "technology"},
            ],
            "discovery_priority": ["rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/graphics/", "/pictures/"],
            "require_date_path": True,
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 12,
            "analysis_rules": {
                "reject_url_substrings": ["/graphics/", "/pictures/", "/fact-check/"],
            },
        },
    },
    "apnews": {
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://apnews.com/sitemap.xml"],
            "section_urls": [
                {"url": "https://apnews.com/world-news", "category": "world"},
                {"url": "https://apnews.com/business", "category": "business"},
            ],
            "discovery_priority": ["news_sitemap", "rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/hub/", "/test-page/", "/live/"],
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 12,
        },
    },
    "bbc": {
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.bbc.com/sitemaps/https-index-com-news.xml"],
            "section_urls": [
                {"url": "https://www.bbc.com/news/world", "category": "world"},
                {"url": "https://www.bbc.com/news/business", "category": "business"},
                {"url": "https://www.bbc.com/news/technology", "category": "technology"},
            ],
            "discovery_priority": ["news_sitemap", "rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/newsround/", "/sport/", "/sounds/", "/iplayer/"],
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 12,
        },
    },
    "aljazeera": {
        "scraper_type": "rss",
        "config": {
            "section_urls": [
                {"url": "https://www.aljazeera.com/news/", "category": "world"},
                {"url": "https://www.aljazeera.com/economy/", "category": "business"},
            ],
            "discovery_priority": ["rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/features/", "/opinions/", "/program/"],
            "require_date_path": True,
            "max_links_per_section": 10,
            "max_detail_enrichment_articles": 10,
        },
    },
    "guardian": {
        "scraper_type": "api",
        "config": {
            "api_base_url": "https://content.guardianapis.com",
            "api_key_env": "GUARDIAN_API_KEY",
            "api_sections": [
                {"section": "world", "category": "world"},
                {"section": "politics", "category": "politics"},
                {"section": "business", "category": "business"},
                {"section": "technology", "category": "technology"},
                {"section": "sport", "category": "sports"},
                {"section": "culture", "category": "entertainment"},
                {"section": "science", "category": "science"},
                {"section": "society", "category": "health"},
            ],
            "discovery_priority": ["api", "rss"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
        },
    },
    "abcnews": {
        "scraper_type": "rss",
        "config": {
            "section_urls": [
                {"url": "https://abcnews.go.com/International", "category": "world"},
                {"url": "https://abcnews.go.com/Business", "category": "business"},
            ],
            "discovery_priority": ["rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/video/", "/gma3/", "/538/"],
            "skip_detail_url_substrings": ["/video/", "/videos/"],
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 10,
            "analysis_rules": {
                "reject_url_substrings": ["/video/", "/videos/", "/gma3/", "/538/"],
            },
        },
    },
    "cbsnews": {
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.cbsnews.com/sitemaps/google-news.xml", "https://www.cbsnews.com/sitemap.xml"],
            "section_urls": [
                {"url": "https://www.cbsnews.com/world/", "category": "world"},
                {"url": "https://www.cbsnews.com/moneywatch/", "category": "business"},
            ],
            "discovery_priority": ["news_sitemap", "rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/essentials/", "/video/"],
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 10,
        },
    },
    "pbs": {
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.pbs.org/newshour/sitemaps.xml"],
            "section_urls": [
                {"url": "https://www.pbs.org/newshour/world", "category": "world"},
                {"url": "https://www.pbs.org/newshour/economy", "category": "business"},
            ],
            "discovery_priority": ["news_sitemap", "rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/show/", "/classroom/", "/video/"],
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 10,
        },
    },
    "bloomberg": {
        "is_active": False,
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.bloomberg.com/sitemap.xml"],
            "section_urls": [
                {"url": "https://www.bloomberg.com/markets", "category": "business"},
                {"url": "https://www.bloomberg.com/politics", "category": "politics"},
            ],
            "discovery_priority": ["news_sitemap", "rss"],
            "detail_policy": "metadata_only",
            "respect_robots": True,
            "analysis_rules": {
                "reject_url_substrings": ["/subscriptions", "/workwise", "/calculator", "/gift-guide"],
                "reject_title_terms": ["subscriptions", "workwise", "gift guide", "calculator", "wealthscore"],
                "evergreen_title_terms": ["2020 china", "2020 chinese new year"],
            },
        },
    },
    "cbssports": {
        "config": {
            "analysis_rules": {
                "force_story_subtype_by_title_terms": {
                    "odds": ["odds", "prediction", "predictions", "picks", "spread", "line"],
                    "admin": ["athletic director", "conference championship", "federation", "president", "commissioner"],
                    "schedule": ["schedule", "fixtures", "dates", "venues"],
                },
            },
        },
    },
    "ft": {
        "is_active": False,
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.ft.com/sitemaps/news.xml", "https://www.ft.com/sitemaps.xml"],
            "section_urls": [
                {"url": "https://www.ft.com/world", "category": "world"},
                {"url": "https://www.ft.com/companies", "category": "business"},
            ],
            "discovery_priority": ["news_sitemap", "rss"],
            "detail_policy": "metadata_only",
            "respect_robots": True,
            "analysis_rules": {
                "reject_url_substrings": ["/stream/", "/myft/", "/podcasts", "/video/"],
            },
        },
    },
    "skysports": {
        "config": {
            "analysis_rules": {
                "reject_url_substrings": ["/watch/", "/video/", "/videos/", "/transfer-centre/", "/live-blog/"],
            },
        },
    },
    "espncricinfo": {
        "is_active": False,
    },
    "wsj": {
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.wsj.com/xml/sitemap.xml"],
            "section_urls": [
                {"url": "https://www.wsj.com/world", "category": "world"},
                {"url": "https://www.wsj.com/business", "category": "business"},
            ],
            "discovery_priority": ["news_sitemap", "rss"],
            "detail_policy": "metadata_only",
            "respect_robots": True,
        },
    },
    "economist": {
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.economist.com/sitemaps.xml"],
            "section_urls": [
                {"url": "https://www.economist.com/international", "category": "world"},
                {"url": "https://www.economist.com/business", "category": "business"},
            ],
            "discovery_priority": ["news_sitemap", "rss"],
            "detail_policy": "metadata_only",
            "respect_robots": True,
        },
    },
}

def deep_merge_dicts(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_source_payload(source_data: dict) -> dict:
    override = SOURCE_DISCOVERY_OVERRIDES.get(source_data["slug"], {})
    payload = dict(source_data)

    base_config = dict(payload.get("config") or {})
    override_config = dict(override.get("config") or {})
    merged_config = deep_merge_dicts(base_config, override_config)

    for key, value in override.items():
        if key == "config":
            continue
        payload[key] = value

    if merged_config:
        payload["config"] = merged_config

    payload.setdefault("scraper_type", "rss")
    payload.setdefault("is_active", source_data.get("slug") not in REMOVED_SOURCE_SLUGS)

    return payload


async def seed():
    async with async_session_factory() as session:
        for source_data in SOURCES:
            if source_data["slug"] in REMOVED_SOURCE_SLUGS:
                print(f"  Skipping {source_data['slug']} (removed source)")
                continue
            existing = await session.execute(
                select(Source).where(Source.slug == source_data["slug"])
            )
            if existing.scalar_one_or_none():
                print(f"  Skipping {source_data['slug']} (already exists)")
                continue

            payload = build_source_payload(source_data)
            is_active = payload.pop("is_active", True)
            source = Source(
                scrape_interval_minutes=60,
                rate_limit_rpm=10,
                is_active=is_active,
                **payload,
            )
            session.add(source)
            print(f"  Added {source_data['name']}")

        await session.commit()
        print("Seed completed!")


if __name__ == "__main__":
    asyncio.run(seed())
