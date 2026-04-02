"""add scrape run discovery stats

Revision ID: 5f1b9c5d4c2e
Revises: 70da29b4070e
Create Date: 2026-04-02 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5f1b9c5d4c2e"
down_revision = "70da29b4070e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scrape_runs",
        sa.Column("detail_enriched_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scrape_runs",
        sa.Column("metadata_only_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scrape_runs",
        sa.Column("discovery_method_used", sa.String(length=50), nullable=True),
    )
    op.alter_column("scrape_runs", "detail_enriched_count", server_default=None)
    op.alter_column("scrape_runs", "metadata_only_count", server_default=None)


def downgrade() -> None:
    op.drop_column("scrape_runs", "discovery_method_used")
    op.drop_column("scrape_runs", "metadata_only_count")
    op.drop_column("scrape_runs", "detail_enriched_count")
