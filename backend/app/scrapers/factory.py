from app.models.source import Source
from app.scrapers.base import BaseNewsScraper
from app.scrapers.sources.abcnews import ABCNewsScraper
from app.scrapers.sources.afp import AFPScraper
from app.scrapers.sources.aljazeera import AlJazeeraScraper
from app.scrapers.sources.apnews import APNewsScraper
from app.scrapers.sources.bbc import BBCScraper
from app.scrapers.sources.bloomberg import BloombergScraper
from app.scrapers.sources.cbsnews import CBSNewsScraper
from app.scrapers.sources.economist import EconomistScraper
from app.scrapers.sources.ft import FTScraper
from app.scrapers.sources.guardian import GuardianScraper
from app.scrapers.sources.pbs import PBSScraper
from app.scrapers.sources.reuters import ReutersScraper
from app.scrapers.sources.wsj import WSJScraper

SCRAPER_MAP: dict[str, type[BaseNewsScraper]] = {
    "reuters": ReutersScraper,
    "apnews": APNewsScraper,
    "afp": AFPScraper,
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


def get_scraper(source: Source) -> BaseNewsScraper:
    """Get the appropriate scraper for a source."""
    scraper_class = SCRAPER_MAP.get(source.slug)
    if not scraper_class:
        # Fallback to generic RSS scraper
        from app.scrapers.rss_scraper import RSSNewsScraper
        return RSSNewsScraper(source)
    return scraper_class(source)
