"""add model confirmed_group_id interest_score to detection

Revision ID: 3db9573168d2
Revises: a52eef39f1b1
Create Date: 2026-07-25 11:41:40.602779

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '3db9573168d2'
down_revision: Union[str, Sequence[str], None] = 'a52eef39f1b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. model — safe for existing rows
    op.add_column(
        "detection",
        sa.Column(
            "model",
            sa.String(),
            nullable=False,
            server_default="birdnet",
        ),
    )
    op.create_index(
        op.f("ix_detection_model"),
        "detection",
        ["model"],
        unique=False,
    )
    # Optional: stop relying on DB default going forward
    op.alter_column("detection", "model", server_default=None)

    # 2. confirmed_group_id (nullable)
    op.add_column(
        "detection",
        sa.Column("confirmed_group_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_detection_confirmed_group_id"),
        "detection",
        ["confirmed_group_id"],
        unique=False,
    )

    # 3. interest_score (nullable)
    op.add_column(
        "detection",
        sa.Column("interest_score", sa.Float(), nullable=True),
    )
    op.create_index(
        op.f("ix_detection_interest_score"),
        "detection",
        ["interest_score"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_detection_model'), table_name='detection')
    op.drop_index(op.f('ix_detection_interest_score'), table_name='detection')
    op.drop_index(op.f('ix_detection_confirmed_group_id'), table_name='detection')
    op.drop_column('detection', 'interest_score')
    op.drop_column('detection', 'confirmed_group_id')
    op.drop_column('detection', 'model')
