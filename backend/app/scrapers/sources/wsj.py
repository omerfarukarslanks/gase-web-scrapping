from app.scrapers.rss_scraper import RSSNewsScraper


class WSJScraper(RSSNewsScraper):
    """Wall Street Journal scraper. Paywall source - RSS provides headlines + summaries only."""
    pass
