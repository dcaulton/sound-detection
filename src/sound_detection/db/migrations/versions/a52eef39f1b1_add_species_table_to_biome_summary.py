"""add species_table to biome_summary

Revision ID: a52eef39f1b1
Revises: 8b97a4a095ba
Create Date: 2026-07-20 10:08:36.788347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a52eef39f1b1'
down_revision: Union[str, Sequence[str], None] = '8b97a4a095ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('biome_summaries', sa.Column('species_table', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('biome_summaries', 'species_table')
