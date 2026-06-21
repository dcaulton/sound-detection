"""add biome_summaries table

Revision ID: fb51cfcef943
Revises: 67f5b02992db
Create Date: 2026-06-21 13:47:48.582735

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'fb51cfcef943'
down_revision: Union[str, Sequence[str], None] = '67f5b02992db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('biome_summaries',
    sa.Column('id', sa.Uuid(), nullable=False), # type: ignore[attr-defined]
    sa.Column('site_id', sa.Uuid(), nullable=False), # type: ignore[attr-defined]
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('window_days', sa.Integer(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False), # type: ignore[attr-defined]
    sa.Column('summary_json', sa.JSON(), nullable=True),
    sa.Column('narrative', sqlmodel.sql.sqltypes.AutoString(), nullable=True), # type: ignore[attr-defined]
    sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True), # type: ignore[attr-defined]
    sa.ForeignKeyConstraint(['site_id'], ['site.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_biome_summaries_site_id'), 'biome_summaries', ['site_id'], unique=False)
    op.create_index(op.f('ix_biome_summaries_status'), 'biome_summaries', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_biome_summaries_status'), table_name='biome_summaries')
    op.drop_index(op.f('ix_biome_summaries_site_id'), table_name='biome_summaries')
    op.drop_table('biome_summaries')
