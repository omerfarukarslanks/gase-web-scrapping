"""Seed script to populate initial news source configurations.

rss_feeds format: [{"url": "...", "category": "..."}]

Standart kategoriler:
  world        - Dünya haberleri
  politics     - Politika, seçimler
  business     - İş dünyası, ekonomi, piyasalar
  technology   - Teknoloji, yapay zeka, siber güvenlik
  sports       - Spor
  entertainment- Kültür, sanat, sinema, yaşam
  science      - Bilim, uzay, çevre
  health       - Sağlık, tıp
  opinion      - Köşe yazıları, analizler
  general      - Karma / sınıflandırılamayan
"""
import asyncio

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models import Article, ScrapeRun, Source  # noqa: F401 - registers all models

SOURCES = [
    # =========================================================================
    # GENERAL NEWS
    # =========================================================================
    {
        "name": "Reuters",
        "slug": "reuters",
        "base_url": "https://www.reuters.com",
        # Resmi RSS 2020'de kapatıldı — Google News proxy kullanılıyor
        "rss_feeds": [
            {"url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&ceid=US:en&hl=en-US&gl=US", "category": "general"},
            {"url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+world&ceid=US:en&hl=en-US&gl=US", "category": "world"},
            {"url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+business&ceid=US:en&hl=en-US&gl=US", "category": "business"},
            {"url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+technology&ceid=US:en&hl=en-US&gl=US", "category": "technology"},
            {"url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+politics&ceid=US:en&hl=en-US&gl=US", "category": "politics"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "AP News",
        "slug": "apnews",
        "base_url": "https://apnews.com",
        # rsshub.ktachibana.party topnews haricinde 503 veriyor — owo.nz mirror kullaniliyor
        "rss_feeds": [
            {"url": "https://rsshub.ktachibana.party/apnews/topics/apf-topnews", "category": "general"},
            {"url": "https://rss.owo.nz/apnews/topics/apf-topnews", "category": "general"},
            {"url": "https://rss.owo.nz/apnews/topics/apf-WorldNews", "category": "world"},
            {"url": "https://rss.owo.nz/apnews/topics/apf-business", "category": "business"},
            {"url": "https://rss.owo.nz/apnews/topics/apf-sports", "category": "sports"},
            {"url": "https://rss.owo.nz/apnews/topics/apf-Health", "category": "health"},
            {"url": "https://rss.owo.nz/apnews/topics/apf-science", "category": "science"},
            {"url": "https://rss.owo.nz/apnews/topics/apf-entertainment", "category": "entertainment"},
            {"url": "https://rss.owo.nz/apnews/topics/apf-politics", "category": "politics"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "France 24",
        "slug": "france24",
        "base_url": "https://www.france24.com",
        # AFP'nin yerine — aynı uluslararası haber kapsama alanı
        "rss_feeds": [
            {"url": "https://www.france24.com/en/rss", "category": "general"},
            {"url": "https://www.france24.com/en/world/rss", "category": "world"},
            {"url": "https://www.france24.com/en/business/rss", "category": "business"},
            {"url": "https://www.france24.com/en/sports/rss", "category": "sports"},
            {"url": "https://www.france24.com/en/health/rss", "category": "health"},
            {"url": "https://www.france24.com/en/culture/rss", "category": "entertainment"},
            {"url": "https://www.france24.com/en/environment/rss", "category": "science"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "BBC News",
        "slug": "bbc",
        "base_url": "https://www.bbc.com/news",
        "rss_feeds": [
            {"url": "https://feeds.bbci.co.uk/news/rss.xml", "category": "general"},
            {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "world"},
            {"url": "https://feeds.bbci.co.uk/news/uk/rss.xml", "category": "politics"},
            {"url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "business"},
            {"url": "https://feeds.bbci.co.uk/news/technology/rss.xml", "category": "technology"},
            {"url": "https://feeds.bbci.co.uk/sport/rss.xml", "category": "sports"},
            {"url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "category": "entertainment"},
            {"url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "category": "science"},
            {"url": "https://feeds.bbci.co.uk/news/health/rss.xml", "category": "health"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "Al Jazeera",
        "slug": "aljazeera",
        "base_url": "https://www.aljazeera.com",
        "rss_feeds": [
            {"url": "https://www.aljazeera.com/xml/rss/all.xml", "category": "general"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "The Guardian",
        "slug": "guardian",
        "base_url": "https://www.theguardian.com",
        "rss_feeds": [
            {"url": "https://www.theguardian.com/world/rss", "category": "world"},
            {"url": "https://www.theguardian.com/us-news/rss", "category": "world"},
            {"url": "https://www.theguardian.com/politics/rss", "category": "politics"},
            {"url": "https://www.theguardian.com/business/rss", "category": "business"},
            {"url": "https://www.theguardian.com/technology/rss", "category": "technology"},
            {"url": "https://www.theguardian.com/sport/rss", "category": "sports"},
            {"url": "https://www.theguardian.com/culture/rss", "category": "entertainment"},
            {"url": "https://www.theguardian.com/lifeandstyle/rss", "category": "entertainment"},
            {"url": "https://www.theguardian.com/science/rss", "category": "science"},
            {"url": "https://www.theguardian.com/environment/rss", "category": "science"},
            {"url": "https://www.theguardian.com/society/health/rss", "category": "health"},
            {"url": "https://www.theguardian.com/commentisfree/rss", "category": "opinion"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "ABC News",
        "slug": "abcnews",
        "base_url": "https://abcnews.go.com",
        "rss_feeds": [
            {"url": "https://abcnews.go.com/abcnews/topstories", "category": "general"},
            {"url": "https://abcnews.go.com/abcnews/internationalheadlines", "category": "world"},
            {"url": "https://abcnews.go.com/abcnews/politicsheadlines", "category": "politics"},
            {"url": "https://abcnews.go.com/abcnews/technologyheadlines", "category": "technology"},
            {"url": "https://abcnews.go.com/abcnews/sportsheadlines", "category": "sports"},
            {"url": "https://abcnews.go.com/abcnews/entertainmentheadlines", "category": "entertainment"},
            {"url": "https://abcnews.go.com/abcnews/healthheadlines", "category": "health"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "CBS News",
        "slug": "cbsnews",
        "base_url": "https://www.cbsnews.com",
        "rss_feeds": [
            {"url": "https://www.cbsnews.com/latest/rss/main", "category": "general"},
            {"url": "https://www.cbsnews.com/latest/rss/world", "category": "world"},
            {"url": "https://www.cbsnews.com/latest/rss/politics", "category": "politics"},
            {"url": "https://www.cbsnews.com/latest/rss/moneywatch", "category": "business"},
            {"url": "https://www.cbsnews.com/latest/rss/technology", "category": "technology"},
            {"url": "https://www.cbsnews.com/latest/rss/entertainment", "category": "entertainment"},
            {"url": "https://www.cbsnews.com/latest/rss/science", "category": "science"},
            {"url": "https://www.cbsnews.com/latest/rss/health", "category": "health"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    {
        "name": "PBS NewsHour",
        "slug": "pbs",
        "base_url": "https://www.pbs.org/newshour",
        "rss_feeds": [
            {"url": "https://www.pbs.org/newshour/feeds/rss/headlines", "category": "general"},
            {"url": "https://www.pbs.org/newshour/feeds/rss/world", "category": "world"},
            {"url": "https://www.pbs.org/newshour/feeds/rss/politics", "category": "politics"},
            {"url": "https://www.pbs.org/newshour/feeds/rss/economy", "category": "business"},
            {"url": "https://www.pbs.org/newshour/feeds/rss/science", "category": "science"},
            {"url": "https://www.pbs.org/newshour/feeds/rss/health", "category": "health"},
            {"url": "https://www.pbs.org/newshour/feeds/rss/arts", "category": "entertainment"},
        ],
        "category": "general",
        "has_paywall": False,
    },
    # =========================================================================
    # FINANCE & ECONOMY
    # =========================================================================
    {
        "name": "Bloomberg",
        "slug": "bloomberg",
        "base_url": "https://www.bloomberg.com",
        "rss_feeds": [
            {"url": "https://feeds.bloomberg.com/markets/news.rss", "category": "business"},
            {"url": "https://feeds.bloomberg.com/politics/news.rss", "category": "politics"},
            {"url": "https://feeds.bloomberg.com/technology/news.rss", "category": "technology"},
            {"url": "https://feeds.bloomberg.com/wealth/news.rss", "category": "business"},
            {"url": "https://feeds.bloomberg.com/green/news.rss", "category": "science"},
        ],
        "category": "finance",
        "has_paywall": True,
    },
    {
        "name": "Financial Times",
        "slug": "ft",
        "base_url": "https://www.ft.com",
        # Yalnizca /rss/home erisilebilir; diger alt kategoriler 403 veriyor
        "rss_feeds": [
            {"url": "https://www.ft.com/rss/home", "category": "general"},
        ],
        "category": "finance",
        "has_paywall": True,
    },
    {
        "name": "Wall Street Journal",
        "slug": "wsj",
        "base_url": "https://www.wsj.com",
        "rss_feeds": [
            {"url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "category": "world"},
            {"url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml", "category": "business"},
            {"url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "category": "business"},
            {"url": "https://feeds.a.dj.com/rss/RSSWSJD.xml", "category": "technology"},
            {"url": "https://feeds.a.dj.com/rss/RSSLifestyle.xml", "category": "entertainment"},
            {"url": "https://feeds.a.dj.com/rss/RSSOpinion.xml", "category": "opinion"},
        ],
        "category": "finance",
        "has_paywall": True,
    },
    {
        "name": "The Economist",
        "slug": "economist",
        "base_url": "https://www.economist.com",
        "rss_feeds": [
            {"url": "https://www.economist.com/latest/rss.xml", "category": "general"},
            {"url": "https://www.economist.com/international/rss.xml", "category": "world"},
            {"url": "https://www.economist.com/finance-and-economics/rss.xml", "category": "business"},
            {"url": "https://www.economist.com/business/rss.xml", "category": "business"},
            {"url": "https://www.economist.com/science-and-technology/rss.xml", "category": "technology"},
            {"url": "https://www.economist.com/culture/rss.xml", "category": "entertainment"},
            {"url": "https://www.economist.com/leaders/rss.xml", "category": "opinion"},
        ],
        "category": "finance",
        "has_paywall": True,
    },
    # =========================================================================
    # SPORTS
    # =========================================================================
    {
        "name": "ESPN",
        "slug": "espn",
        "base_url": "https://www.espn.com",
        "rss_feeds": [
            {"url": "https://www.espn.com/espn/rss/news", "category": "sports"},
            {"url": "https://www.espn.com/espn/rss/soccer/news", "category": "sports"},
            {"url": "https://www.espn.com/espn/rss/nfl/news", "category": "sports"},
            {"url": "https://www.espn.com/espn/rss/nba/news", "category": "sports"},
            {"url": "https://www.espn.com/espn/rss/tennis/news", "category": "sports"},
            {"url": "https://www.espn.com/espn/rss/golf/news", "category": "sports"},
            {"url": "https://www.espn.com/espn/rss/f1/news", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "CBS Sports",
        "slug": "cbssports",
        "base_url": "https://www.cbssports.com",
        "rss_feeds": [
            {"url": "https://www.cbssports.com/rss/headlines", "category": "sports"},
            {"url": "https://www.cbssports.com/rss/headlines/soccer", "category": "sports"},
            {"url": "https://www.cbssports.com/rss/headlines/nfl", "category": "sports"},
            {"url": "https://www.cbssports.com/rss/headlines/nba", "category": "sports"},
            {"url": "https://www.cbssports.com/rss/headlines/golf", "category": "sports"},
            {"url": "https://www.cbssports.com/rss/headlines/tennis", "category": "sports"},
            {"url": "https://www.cbssports.com/rss/headlines/nhl", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "Yahoo Sports",
        "slug": "yahoosports",
        "base_url": "https://sports.yahoo.com",
        "rss_feeds": [
            {"url": "https://sports.yahoo.com/rss", "category": "sports"},
            {"url": "https://sports.yahoo.com/soccer/rss.xml", "category": "sports"},
            {"url": "https://sports.yahoo.com/nfl/rss.xml", "category": "sports"},
            {"url": "https://sports.yahoo.com/nba/rss.xml", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "Sky Sports",
        "slug": "skysports",
        "base_url": "https://www.skysports.com",
        "rss_feeds": [
            {"url": "https://www.skysports.com/rss/12040", "category": "sports"},
            {"url": "https://www.skysports.com/rss/11095", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "ESPN Cricinfo",
        "slug": "espncricinfo",
        "base_url": "https://www.espncricinfo.com",
        "rss_feeds": [
            {"url": "https://www.espncricinfo.com/rss/content/story/feeds/0.xml", "category": "sports"},
            {"url": "https://www.espncricinfo.com/rss/content/story/feeds/6.xml", "category": "sports"},  # India
            {"url": "https://www.espncricinfo.com/rss/content/story/feeds/2.xml", "category": "sports"},  # Australia
            {"url": "https://www.espncricinfo.com/rss/content/story/feeds/1.xml", "category": "sports"},  # England
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "Marca English",
        "slug": "marca",
        "base_url": "https://www.marca.com/en",
        # e00-marca CDN subfeedi 404 veriyor — yalnizca ana feed
        "rss_feeds": [
            {"url": "https://www.marca.com/rss/portada.xml", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "AS English",
        "slug": "asenglish",
        "base_url": "https://en.as.com",
        "rss_feeds": [
            {"url": "https://en.as.com/rss/", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "L'Equipe",
        "slug": "lequipe",
        "base_url": "https://www.lequipe.fr",
        "rss_feeds": [
            {"url": "https://www.lequipe.fr/rss/actu_rss.xml", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "Cricbuzz",
        "slug": "cricbuzz",
        "base_url": "https://www.cricbuzz.com",
        "rss_feeds": [
            {"url": "https://www.cricbuzz.com/cricket-rss-feeds", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
    {
        "name": "Globo Esporte",
        "slug": "globo",
        "base_url": "https://ge.globo.com",
        "rss_feeds": [
            {"url": "https://ge.globo.com/rss/feed.xml", "category": "sports"},
            {"url": "https://ge.globo.com/futebol/index.xml", "category": "sports"},
        ],
        "category": "sports",
        "has_paywall": False,
    },
]


SOURCE_DISCOVERY_OVERRIDES = {
    "reuters": {
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
        },
    },
    "apnews": {
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://apnews.com/sitemap.xml"],
            "section_urls": [
                {"url": "https://apnews.com/world-news", "category": "world"},
                {"url": "https://apnews.com/business", "category": "business"},
                {"url": "https://apnews.com/politics", "category": "politics"},
            ],
            "discovery_priority": ["news_sitemap", "rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/hub/", "/test-page/"],
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 12,
        },
    },
    "france24": {
        "scraper_type": "rss",
        "config": {
            "section_urls": [
                {"url": "https://www.france24.com/en/world/", "category": "world"},
                {"url": "https://www.france24.com/en/business/", "category": "business"},
                {"url": "https://www.france24.com/en/middle-east/", "category": "world"},
            ],
            "discovery_priority": ["rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "require_date_path": True,
            "exclude_url_substrings": [
                "/replay/",
                "/sponsored",
                "/news-alerts",
                "/settings",
                "/programs/",
            ],
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 10,
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
                {"section": "commentisfree", "category": "opinion"},
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
                {"url": "https://abcnews.go.com/Politics", "category": "politics"},
                {"url": "https://abcnews.go.com/Business", "category": "business"},
            ],
            "discovery_priority": ["rss", "section_html"],
            "detail_policy": "open_page_only",
            "respect_robots": True,
            "exclude_url_substrings": ["/video/", "/gma3/", "/538/"],
            "skip_detail_url_substrings": ["/video/", "/videos/"],
            "max_links_per_section": 12,
            "max_detail_enrichment_articles": 10,
        },
    },
    "cbsnews": {
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.cbsnews.com/sitemaps/google-news.xml", "https://www.cbsnews.com/sitemap.xml"],
            "section_urls": [
                {"url": "https://www.cbsnews.com/world/", "category": "world"},
                {"url": "https://www.cbsnews.com/politics/", "category": "politics"},
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
                {"url": "https://www.pbs.org/newshour/politics", "category": "politics"},
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
        "scraper_type": "news_sitemap",
        "config": {
            "sitemap_urls": ["https://www.bloomberg.com/sitemap.xml"],
            "section_urls": [
                {"url": "https://www.bloomberg.com/markets", "category": "business"},
                {"url": "https://www.bloomberg.com/politics", "category": "politics"},
                {"url": "https://www.bloomberg.com/technology", "category": "technology"},
            ],
            "discovery_priority": ["news_sitemap", "rss"],
            "detail_policy": "metadata_only",
            "respect_robots": True,
        },
    },
    "ft": {
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
        },
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


def build_source_payload(source_data: dict) -> dict:
    override = SOURCE_DISCOVERY_OVERRIDES.get(source_data["slug"], {})
    payload = dict(source_data)

    base_config = dict(payload.get("config") or {})
    override_config = dict(override.get("config") or {})
    merged_config = {**base_config, **override_config}

    for key, value in override.items():
        if key == "config":
            continue
        payload[key] = value

    if merged_config:
        payload["config"] = merged_config

    payload.setdefault("scraper_type", "rss")

    return payload


async def seed():
    async with async_session_factory() as session:
        for source_data in SOURCES:
            existing = await session.execute(
                select(Source).where(Source.slug == source_data["slug"])
            )
            if existing.scalar_one_or_none():
                print(f"  Skipping {source_data['slug']} (already exists)")
                continue

            payload = build_source_payload(source_data)
            source = Source(
                scrape_interval_minutes=60,
                rate_limit_rpm=10,
                is_active=True,
                **payload,
            )
            session.add(source)
            print(f"  Added {source_data['name']}")

        await session.commit()
        print("Seed completed!")


if __name__ == "__main__":
    asyncio.run(seed())
