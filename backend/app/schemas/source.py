import uuid
from datetime import datetime

from pydantic import BaseModel


class RssFeedEntry(BaseModel):
    """Kategorize edilmis RSS feed girisi: {"url": "...", "category": "..."}"""
    url: str
    category: str | None = None


class SourceBase(BaseModel):
    name: str
    slug: str
    base_url: str
    # Geriye donuk uyumluluk: eski format str listesi, yeni format dict listesi
    rss_feeds: list[RssFeedEntry | str] = []
    scraper_type: str = "rss"
    category: str = "general"
    is_active: bool = True
    scrape_interval_minutes: int = 60
    rate_limit_rpm: int = 10
    has_paywall: bool = False
    config: dict | None = None


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    is_active: bool | None = None
    scrape_interval_minutes: int | None = None
    rate_limit_rpm: int | None = None
    rss_feeds: list[RssFeedEntry | str] | None = None
    scraper_type: str | None = None
    config: dict | None = None


class SourceResponse(SourceBase):
    id: uuid.UUID
    last_scraped_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceWithStats(SourceResponse):
    articles_today: int = 0
    total_articles: int = 0
    last_run_status: str | None = None
