"""normalize_slot_saved_path_to_basename

Revision ID: 2cf4ef820e46
Revises: c3d4e5f6g7h8
Create Date: 2026-04-17 11:02:11.382973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2cf4ef820e46'
down_revision: Union[str, None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE sessions
        SET slot_saved_path = substr(
            slot_saved_path,
            length(rtrim(slot_saved_path, replace(slot_saved_path, '/', ''))) + 1
        )
        WHERE slot_saved_path IS NOT NULL AND slot_saved_path LIKE '%/%'
    """)


def downgrade() -> None:
    # Basename normalization is irreversible without the original paths.
    pass
