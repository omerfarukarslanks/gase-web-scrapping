"""add topic feedback

Revision ID: 9d2c6f8a4b11
Revises: 5f1b9c5d4c2e
Create Date: 2026-04-02 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d2c6f8a4b11"
down_revision = "5f1b9c5d4c2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_feedback",
        sa.Column("topic_id", sa.String(length=40), nullable=False),
        sa.Column("feedback_label", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("headline_tr", sa.String(length=500), nullable=False),
        sa.Column("summary_tr", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("aggregation_type", sa.String(length=20), nullable=False),
        sa.Column("quality_status", sa.String(length=20), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False),
        sa.Column("source_slugs", sa.JSON(), nullable=False),
        sa.Column("representative_article_ids", sa.JSON(), nullable=False),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("score_features", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_topic_feedback_feedback_label"), "topic_feedback", ["feedback_label"], unique=False)
    op.create_index(op.f("ix_topic_feedback_topic_id"), "topic_feedback", ["topic_id"], unique=True)
    op.create_index(op.f("ix_topic_feedback_category"), "topic_feedback", ["category"], unique=False)
    op.create_index(op.f("ix_topic_feedback_quality_status"), "topic_feedback", ["quality_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_topic_feedback_quality_status"), table_name="topic_feedback")
    op.drop_index(op.f("ix_topic_feedback_category"), table_name="topic_feedback")
    op.drop_index(op.f("ix_topic_feedback_topic_id"), table_name="topic_feedback")
    op.drop_index(op.f("ix_topic_feedback_feedback_label"), table_name="topic_feedback")
    op.drop_table("topic_feedback")
