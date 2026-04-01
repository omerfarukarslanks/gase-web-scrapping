from app.scrapers.rss_scraper import RSSNewsScraper


class ReutersScraper(RSSNewsScraper):
    """Reuters news scraper."""

    def parse_category(self, entry) -> str | None:
        category = super().parse_category(entry)
        if category:
            return category.lower()
        # Infer from feed URL
        return None
