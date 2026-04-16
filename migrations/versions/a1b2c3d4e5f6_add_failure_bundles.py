"""add failure_bundles table

Revision ID: a1b2c3d4e5f6
Revises: 7368d8100cae
Create Date: 2026-04-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "7368d8100cae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "failure_bundles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("failure_class", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("tool_chain", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_failure_bundles_class", "failure_bundles", ["failure_class"], unique=False
    )
    op.create_index(
        "idx_failure_bundles_created", "failure_bundles", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_failure_bundles_created", table_name="failure_bundles")
    op.drop_index("idx_failure_bundles_class", table_name="failure_bundles")
    op.drop_table("failure_bundles")
