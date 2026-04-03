import uuid

from sqlalchemy import Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class TopicFeedback(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "topic_feedback"

    topic_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    feedback_label: Mapped[str] = mapped_column(String(20), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline_tr: Mapped[str] = mapped_column(String(500))
    summary_tr: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), index=True)
    aggregation_type: Mapped[str] = mapped_column(String(20))
    quality_status: Mapped[str] = mapped_column(String(20), index=True)
    quality_score: Mapped[float] = mapped_column(Float)
    video_quality_status: Mapped[str] = mapped_column(String(20), index=True)
    video_quality_score: Mapped[int] = mapped_column(Integer)
    source_count: Mapped[int] = mapped_column(Integer)
    article_count: Mapped[int] = mapped_column(Integer)
    source_slugs: Mapped[list] = mapped_column(JSON, default=list)
    representative_article_ids: Mapped[list] = mapped_column(JSON, default=list)
    review_reasons: Mapped[list] = mapped_column(JSON, default=list)
    video_review_reasons: Mapped[list] = mapped_column(JSON, default=list)
    score_features: Mapped[dict] = mapped_column(JSON, default=dict)
