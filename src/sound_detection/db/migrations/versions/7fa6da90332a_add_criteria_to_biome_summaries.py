"""add criteria to biome_summaries

Revision ID: 7fa6da90332a
Revises: 3db9573168d2
Create Date: 2026-10-31 15:14:55.696739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7fa6da90332a'
down_revision: Union[str, Sequence[str], None] = '3db9573168d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('biome_summaries', sa.Column('criteria', sa.JSON(), nullable=True))



def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('biome_summaries', 'criteria')
