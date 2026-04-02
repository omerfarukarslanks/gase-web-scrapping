"""add article detail fields

Revision ID: 0a6f4c2d91bb
Revises: 9d2c6f8a4b11
Create Date: 2026-04-02 23:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0a6f4c2d91bb"
down_revision = "9d2c6f8a4b11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("content_text", sa.Text(), nullable=True))
    op.add_column(
        "articles",
        sa.Column("detail_enriched", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("articles", sa.Column("detail_fetched_at", sa.DateTime(), nullable=True))
    op.alter_column("articles", "detail_enriched", server_default=None)


def downgrade() -> None:
    op.drop_column("articles", "detail_fetched_at")
    op.drop_column("articles", "detail_enriched")
    op.drop_column("articles", "content_text")
