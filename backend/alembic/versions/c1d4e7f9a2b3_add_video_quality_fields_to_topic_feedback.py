"""add video quality fields to topic feedback

Revision ID: c1d4e7f9a2b3
Revises: 4b3c2d1e9f70
Create Date: 2026-04-03 17:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1d4e7f9a2b3"
down_revision = "4b3c2d1e9f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("topic_feedback", sa.Column("video_quality_status", sa.String(length=20), nullable=True))
    op.add_column("topic_feedback", sa.Column("video_quality_score", sa.Integer(), nullable=True))
    op.add_column("topic_feedback", sa.Column("video_review_reasons", sa.JSON(), nullable=True))

    op.execute(
        """
        UPDATE topic_feedback
        SET video_quality_status = quality_status,
            video_quality_score = GREATEST(0, LEAST(100, ROUND(quality_score * 100))),
            video_review_reasons = review_reasons
        """
    )

    op.alter_column("topic_feedback", "video_quality_status", nullable=False)
    op.alter_column("topic_feedback", "video_quality_score", nullable=False)
    op.alter_column("topic_feedback", "video_review_reasons", nullable=False)
    op.create_index(
        op.f("ix_topic_feedback_video_quality_status"),
        "topic_feedback",
        ["video_quality_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_topic_feedback_video_quality_status"), table_name="topic_feedback")
    op.drop_column("topic_feedback", "video_review_reasons")
    op.drop_column("topic_feedback", "video_quality_score")
    op.drop_column("topic_feedback", "video_quality_status")
