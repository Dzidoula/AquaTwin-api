"""add emitter_flow_lh and auto_recommend_enabled to fields

Revision ID: d4e2f8a01b3c
Revises: a1c9f3d7b204
Create Date: 2026-09-04 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e2f8a01b3c'
down_revision: Union[str, Sequence[str], None] = 'a1c9f3d7b204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fields', sa.Column('emitter_flow_lh', sa.Float(), nullable=True))
    op.add_column(
        'fields',
        sa.Column('auto_recommend_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('fields', 'auto_recommend_enabled')
    op.drop_column('fields', 'emitter_flow_lh')
