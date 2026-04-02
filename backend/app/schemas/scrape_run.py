import uuid
from datetime import datetime

from pydantic import BaseModel


class ScrapeRunResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    status: str
    articles_found: int
    articles_new: int
    articles_updated: int
    detail_enriched_count: int
    metadata_only_count: int
    discovery_method_used: str | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    created_at: datetime
    source_name: str | None = None
    source_slug: str | None = None

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    total_articles: int
    articles_today: int
    active_sources: int
    total_sources: int
    last_scrape_at: datetime | None = None
    articles_by_source: list[dict]
    articles_by_category: list[dict]
    recent_runs: list[ScrapeRunResponse]
