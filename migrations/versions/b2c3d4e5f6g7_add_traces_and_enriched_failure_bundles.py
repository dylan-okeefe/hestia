"""add traces table and enriched failure_bundles columns

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6g7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add enriched columns to failure_bundles
    op.add_column(
        "failure_bundles",
        sa.Column("request_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "failure_bundles",
        sa.Column("policy_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "failure_bundles",
        sa.Column("slot_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "failure_bundles",
        sa.Column("trace_id", sa.String(), nullable=True),
    )

    # Create traces table
    op.create_table(
        "traces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("user_input_summary", sa.Text(), nullable=False),
        sa.Column("tools_called", sa.Text(), nullable=False),
        sa.Column("tool_call_count", sa.Integer(), nullable=False),
        sa.Column("delegated", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("artifact_handles", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("total_duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_traces_session", "traces", ["session_id", "started_at"], unique=False)
    op.create_index("idx_traces_turn", "traces", ["turn_id"], unique=False)
    op.create_index("idx_traces_outcome", "traces", ["outcome"], unique=False)
    op.create_index("idx_traces_created", "traces", ["started_at"], unique=False)


def downgrade() -> None:
    # Drop traces table and indexes
    op.drop_index("idx_traces_created", table_name="traces")
    op.drop_index("idx_traces_outcome", table_name="traces")
    op.drop_index("idx_traces_turn", table_name="traces")
    op.drop_index("idx_traces_session", table_name="traces")
    op.drop_table("traces")

    # Drop enriched columns from failure_bundles
    op.drop_column("failure_bundles", "trace_id")
    op.drop_column("failure_bundles", "slot_snapshot")
    op.drop_column("failure_bundles", "policy_snapshot")
    op.drop_column("failure_bundles", "request_summary")
