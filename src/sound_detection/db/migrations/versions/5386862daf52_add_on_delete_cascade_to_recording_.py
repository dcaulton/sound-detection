"""add on delete cascade to recording.microphone_id

Revision ID: 5386862daf52
Revises: 2bb00645199d
Create Date: 2026-06-09 14:04:12.379497

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5386862daf52'
down_revision: Union[str, Sequence[str], None] = '2bb00645199d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "recording_microphone_id_fkey",
        "recording",
        type_="foreignkey"
    )
    op.create_foreign_key(
        "recording_microphone_id_fkey",
        "recording",
        "microphone",
        ["microphone_id"],
        ["id"],
        ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint(
        "recording_microphone_id_fkey",
        "recording",
        type_="foreignkey"
    )
    op.create_foreign_key(
        "recording_microphone_id_fkey",
        "recording",
        "microphone",
        ["microphone_id"],
        ["id"]
    )
