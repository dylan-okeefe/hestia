"""add_is_handoff_to_messages

Revision ID: 60465f741bc1
Revises: 7e9d51725dbc
Create Date: 2026-05-31 01:29:11.901118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60465f741bc1'
down_revision: Union[str, None] = '7e9d51725dbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("is_handoff", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("messages", "is_handoff")
