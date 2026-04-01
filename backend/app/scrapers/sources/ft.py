from app.scrapers.rss_scraper import RSSNewsScraper


class FTScraper(RSSNewsScraper):
    """Financial Times scraper. Paywall source - RSS provides headlines + summaries only."""
    pass
