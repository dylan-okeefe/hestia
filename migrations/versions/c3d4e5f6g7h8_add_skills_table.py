"""add skills table

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-04-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6g7h8"
down_revision: Union[str, None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create skills table
    op.create_table(
        "skills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("capabilities", sa.Text(), nullable=False),
        sa.Column("required_tools", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("idx_skills_state", "skills", ["state"], unique=False)
    op.create_index("idx_skills_name", "skills", ["name"], unique=False)


def downgrade() -> None:
    # Drop skills table and indexes
    op.drop_index("idx_skills_name", table_name="skills")
    op.drop_index("idx_skills_state", table_name="skills")
    op.drop_table("skills")
