"""add scrape run snapshots

Revision ID: 4b3c2d1e9f70
Revises: 0a6f4c2d91bb
Create Date: 2026-04-03 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4b3c2d1e9f70"
down_revision = "0a6f4c2d91bb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scrape_runs", sa.Column("source_name_snapshot", sa.String(length=100), nullable=True))
    op.add_column("scrape_runs", sa.Column("source_slug_snapshot", sa.String(length=50), nullable=True))
    op.add_column("scrape_runs", sa.Column("source_category_snapshot", sa.String(length=20), nullable=True))
    op.create_index(
        op.f("ix_scrape_runs_source_slug_snapshot"),
        "scrape_runs",
        ["source_slug_snapshot"],
        unique=False,
    )

    op.execute(
        """
        UPDATE scrape_runs AS sr
        SET source_name_snapshot = s.name,
            source_slug_snapshot = s.slug,
            source_category_snapshot = s.category
        FROM sources AS s
        WHERE sr.source_id = s.id
        """
    )

    op.alter_column("scrape_runs", "source_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM scrape_runs WHERE source_id IS NULL")
    op.alter_column("scrape_runs", "source_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index(op.f("ix_scrape_runs_source_slug_snapshot"), table_name="scrape_runs")
    op.drop_column("scrape_runs", "source_category_snapshot")
    op.drop_column("scrape_runs", "source_slug_snapshot")
    op.drop_column("scrape_runs", "source_name_snapshot")
