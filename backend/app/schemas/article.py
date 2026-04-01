import uuid
from datetime import datetime

from pydantic import BaseModel


class ArticleBase(BaseModel):
    title: str
    url: str
    summary: str | None = None
    content_snippet: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    image_url: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    language: str = "en"
    source_category: str = "general"


class ArticleResponse(ArticleBase):
    id: uuid.UUID
    source_id: uuid.UUID
    url_hash: str
    scraped_at: datetime
    created_at: datetime
    source_name: str | None = None
    source_slug: str | None = None
    has_paywall: bool = False

    model_config = {"from_attributes": True}


class ArticleListResponse(BaseModel):
    items: list[ArticleResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ArticleFilters(BaseModel):
    source: str | None = None
    category: str | None = None
    source_category: str | None = None
    search: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    language: str | None = None
