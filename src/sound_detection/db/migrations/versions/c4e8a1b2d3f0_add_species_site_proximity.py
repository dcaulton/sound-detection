"""add species_site_proximity table

Revision ID: c4e8a1b2d3f0
Revises: 7fa6da90332a
Create Date: 2026-11-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4e8a1b2d3f0"
down_revision: Union[str, Sequence[str], None] = "7fa6da90332a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "species_site_proximity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("scientific_name", sa.String(length=200), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("distance_miles", sa.Float(), nullable=True),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.Column("observed_on", sa.Date(), nullable=True),
        sa.Column("observation_lat", sa.Float(), nullable=True),
        sa.Column("observation_lon", sa.Float(), nullable=True),
        sa.Column("quality_grade", sa.String(), nullable=True),
        sa.Column("place_guess", sa.String(), nullable=True),
        sa.Column("search_radius_km", sa.Float(), nullable=False, server_default="160"),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "scientific_name", name="uq_site_species_proximity"),
    )
    op.create_index(
        op.f("ix_species_site_proximity_site_id"),
        "species_site_proximity",
        ["site_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_species_site_proximity_scientific_name"),
        "species_site_proximity",
        ["scientific_name"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_species_site_proximity_scientific_name"), table_name="species_site_proximity")
    op.drop_index(op.f("ix_species_site_proximity_site_id"), table_name="species_site_proximity")
    op.drop_table("species_site_proximity")
