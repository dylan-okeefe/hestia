"""add_session_title

Revision ID: e3f4a5b6c7d8
Revises: 60465f741bc1
Create Date: 2026-06-06 15:49:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = '60465f741bc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("title", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "title")
