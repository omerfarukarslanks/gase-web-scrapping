import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ScrapeRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scrape_runs"

    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    source_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_slug_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_category_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    articles_found: Mapped[int] = mapped_column(Integer, default=0)
    articles_new: Mapped[int] = mapped_column(Integer, default=0)
    articles_updated: Mapped[int] = mapped_column(Integer, default=0)
    detail_enriched_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_only_count: Mapped[int] = mapped_column(Integer, default=0)
    discovery_method_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    source = relationship("Source", back_populates="scrape_runs")
