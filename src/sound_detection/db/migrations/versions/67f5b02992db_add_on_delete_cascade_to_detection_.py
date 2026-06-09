"""add on delete cascade to detection.recording_id

Revision ID: 67f5b02992db
Revises: 5386862daf52
Create Date: 2026-06-09 14:12:17.198972

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67f5b02992db'
down_revision: Union[str, Sequence[str], None] = '5386862daf52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "detection_recording_id_fkey",
        "detection",
        type_="foreignkey"
    )
    op.create_foreign_key(
        "detection_recording_id_fkey",
        "detection",
        "recording",
        ["recording_id"],
        ["id"],
        ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint(
        "detection_recording_id_fkey",
        "detection",
        type_="foreignkey"
    )
    op.create_foreign_key(
        "detection_recording_id_fkey",
        "detection",
        "recording",
        ["recording_id"],
        ["id"]
    )
