"""add human_narrative, images and grok_narrative to biome_summary

Revision ID: 8b97a4a095ba
Revises: fb51cfcef943
Create Date: 2026-07-19 11:13:34.294760

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '8b97a4a095ba'
down_revision: Union[str, Sequence[str], None] = 'fb51cfcef943'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('biome_summaries', sa.Column('human_narrative', sqlmodel.sql.sqltypes.AutoString(), nullable=True)) #type: ignore[attr-defined]
    op.add_column('biome_summaries', sa.Column('notable_species_images', sa.JSON(), nullable=True))
    op.add_column('biome_summaries', sa.Column('grok_narrative', sqlmodel.sql.sqltypes.AutoString(), nullable=True)) #type: ignore[attr-defined]


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('biome_summaries', 'grok_narrative')
    op.drop_column('biome_summaries', 'notable_species_images')
    op.drop_column('biome_summaries', 'human_narrative')
