import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Article(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "articles"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    title: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(2000))
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    scraped_at: Mapped[datetime] = mapped_column()
    image_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    source_category: Mapped[str] = mapped_column(String(20), default="general")
    raw_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    source = relationship("Source", back_populates="articles")

    __table_args__ = (
        Index("ix_articles_source_published", "source_id", "published_at"),
    )
