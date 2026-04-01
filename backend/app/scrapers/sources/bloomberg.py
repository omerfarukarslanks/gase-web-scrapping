from app.scrapers.rss_scraper import RSSNewsScraper


class BloombergScraper(RSSNewsScraper):
    """Bloomberg scraper. Paywall source - RSS provides headlines + summaries only."""
    pass
