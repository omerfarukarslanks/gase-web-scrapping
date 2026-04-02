from app.scrapers.configurable_scraper import ConfigurableNewsScraper
from app.models.source import Source
from app.scrapers.base import BaseNewsScraper
from app.scrapers.sources.abcnews import ABCNewsScraper
from app.scrapers.sources.aljazeera import AlJazeeraScraper
from app.scrapers.sources.apnews import APNewsScraper
from app.scrapers.sources.bbc import BBCScraper
from app.scrapers.sources.bloomberg import BloombergScraper
from app.scrapers.sources.cbsnews import CBSNewsScraper
from app.scrapers.sources.economist import EconomistScraper
from app.scrapers.sources.france24 import France24Scraper
from app.scrapers.sources.ft import FTScraper
from app.scrapers.sources.guardian import GuardianScraper
from app.scrapers.sources.pbs import PBSScraper
from app.scrapers.sources.reuters import ReutersScraper
from app.scrapers.sources.wsj import WSJScraper

SCRAPER_MAP: dict[str, type[BaseNewsScraper]] = {
    "reuters": ReutersScraper,
    "apnews": APNewsScraper,
    "france24": France24Scraper,
    "bbc": BBCScraper,
    "aljazeera": AlJazeeraScraper,
    "guardian": GuardianScraper,
    "abcnews": ABCNewsScraper,
    "cbsnews": CBSNewsScraper,
    "pbs": PBSScraper,
    "bloomberg": BloombergScraper,
    "ft": FTScraper,
    "wsj": WSJScraper,
    "economist": EconomistScraper,
}


def get_rss_scraper(source: Source) -> BaseNewsScraper:
    scraper_class = SCRAPER_MAP.get(source.slug)
    if not scraper_class:
        from app.scrapers.rss_scraper import RSSNewsScraper
        return RSSNewsScraper(source)
    return scraper_class(source)


def get_scraper(source: Source):
    """Get the appropriate scraper for a source."""
    config = source.config or {}
    if source.scraper_type != "rss" or config.get("discovery_priority"):
        return ConfigurableNewsScraper(source, get_rss_scraper)
    return get_rss_scraper(source)
