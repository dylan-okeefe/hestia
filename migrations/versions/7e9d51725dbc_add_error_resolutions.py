"""add error_resolutions

Revision ID: 7e9d51725dbc
Revises: d4e5f6g7h8i9
Create Date: 2026-05-19 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e9d51725dbc'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'error_resolutions',
        sa.Column('error_id', sa.String(), primary_key=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('resolved_by', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('error_resolutions')
