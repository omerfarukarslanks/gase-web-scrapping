from app.scrapers.rss_scraper import RSSNewsScraper


class BBCScraper(RSSNewsScraper):
    """BBC News scraper. BBC has well-structured RSS feeds."""

    def parse_category(self, entry) -> str | None:
        category = super().parse_category(entry)
        if category:
            return category.lower()
        return None
