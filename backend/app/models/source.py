import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Source(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    rss_feeds: Mapped[list] = mapped_column(JSON, default=list)
    scraper_type: Mapped[str] = mapped_column(String(20), default="rss")
    category: Mapped[str] = mapped_column(String(20), default="general")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scrape_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=10)
    has_paywall: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(nullable=True)

    articles = relationship("Article", back_populates="source")
    scrape_runs = relationship("ScrapeRun", back_populates="source")
