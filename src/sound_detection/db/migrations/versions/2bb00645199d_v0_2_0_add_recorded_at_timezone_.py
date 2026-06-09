"""v0.2.0 add recorded_at, timezone, detection absolute times + timestamps

Revision ID: 2bb00645199d
Revises: 76e200341ff6
Create Date: 2026-06-09 10:18:53.309076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2bb00645199d'
down_revision: Union[str, Sequence[str], None] = '76e200341ff6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # === DETECTION TABLE ===
    # New columns with safe defaults
    op.add_column('detection', sa.Column('start_offset', sa.Float(), nullable=False, server_default=sa.text('0')))
    op.add_column('detection', sa.Column('end_offset', sa.Float(), nullable=False, server_default=sa.text('0')))
    op.add_column('detection', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column('detection', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))

    # Type change from numeric epoch → timestamp (already had the USING clause)
    op.alter_column('detection', 'start_time',
        existing_type=sa.DOUBLE_PRECISION(precision=53),
        type_=sa.DateTime(),
        nullable=True,
        postgresql_using='to_timestamp(start_time)'
    )
    op.alter_column('detection', 'end_time',
        existing_type=sa.DOUBLE_PRECISION(precision=53),
        type_=sa.DateTime(),
        nullable=True,
        postgresql_using='to_timestamp(end_time)'
    )

    # === MICROPHONE TABLE ===
    op.add_column('microphone', sa.Column('filename_datetime_format', sqlmodel.sql.sqltypes.AutoString(), nullable=True)) # type: ignore[attr-defined]
    op.add_column('microphone', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column('microphone', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))

    # === RECORDING TABLE ===
    op.add_column('recording', sa.Column('recorded_at', sa.DateTime(), nullable=True))
    op.add_column('recording', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column('recording', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))

    # === SITE TABLE ===
    op.add_column('site', sa.Column('timezone', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("'UTC'"))) # type: ignore[attr-defined]
    op.add_column('site', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column('site', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))

    # Making these NOT NULL is risky if any rows have NULLs.
    # For safety, we're commenting them out for now.
    # op.alter_column('site', 'latitude', existing_type=sa.DOUBLE_PRECISION(precision=53), nullable=False)
    # op.alter_column('site', 'longitude', existing_type=sa.DOUBLE_PRECISION(precision=53), nullable=False)

def downgrade() -> None:
    """Downgrade schema."""

    # === Reverse type changes on detection (timestamp → numeric) ===
    # Using extract(epoch ...) to convert back to Unix timestamp (seconds)
    op.alter_column('detection', 'end_time',
        existing_type=sa.DateTime(),
        type_=sa.DOUBLE_PRECISION(precision=53),
        nullable=False,
        postgresql_using='extract(epoch from end_time)'
    )
    op.alter_column('detection', 'start_time',
        existing_type=sa.DateTime(),
        type_=sa.DOUBLE_PRECISION(precision=53),
        nullable=False,
        postgresql_using='extract(epoch from start_time)'
    )

    # === Drop columns we added ===
    op.drop_column('detection', 'updated_at')
    op.drop_column('detection', 'created_at')
    op.drop_column('detection', 'end_offset')
    op.drop_column('detection', 'start_offset')

    op.drop_column('microphone', 'updated_at')
    op.drop_column('microphone', 'created_at')
    op.drop_column('microphone', 'filename_datetime_format')

    op.drop_column('recording', 'updated_at')
    op.drop_column('recording', 'created_at')
    op.drop_column('recording', 'recorded_at')

    op.drop_column('site', 'updated_at')
    op.drop_column('site', 'created_at')
    op.drop_column('site', 'timezone')

    # Note: We intentionally left the latitude/longitude NOT NULL changes out of upgrade,
    # so there is nothing to reverse here.
