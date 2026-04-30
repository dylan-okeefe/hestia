"""add_scheduled_task_notify

Revision ID: d4e5f6g7h8i9
Revises: 2cf4ef820e46
Create Date: 2026-04-22 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, None] = '2cf4ef820e46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scheduled_tasks', sa.Column('notify', sa.Boolean, nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('scheduled_tasks', 'notify')
