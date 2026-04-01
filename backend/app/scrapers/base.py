from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ScrapedArticle:
    title: str
    url: str
    summary: str | None = None
    content_snippet: str | None = None
    author: str | None = None
    published_at: str | None = None
    image_url: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    language: str = "en"
    raw_metadata: dict | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class BaseNewsScraper(ABC):
    source_slug: str
    source_name: str

    def __init__(self, source):
        self.source = source
        self.source_slug = source.slug
        self.source_name = source.name

    @abstractmethod
    async def fetch_articles(self) -> list[dict]:
        """Fetch articles from the source. Returns list of article dicts."""
        ...
