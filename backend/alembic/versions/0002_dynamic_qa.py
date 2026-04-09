"""iter_3.1_dynamic_qa_fields

Revision ID: 0002_dynamic_qa
Revises: 0001_initial
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_dynamic_qa'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 给 guide_sessions 表增加动态问答所需字段
    op.add_column(
        'guide_sessions',
        sa.Column(
            'conversation_history',
            sa.JSON(),
            nullable=True,
            server_default='[]',
        )
    )
    op.add_column(
        'guide_sessions',
        sa.Column(
            'mode',
            sa.String(20),
            nullable=True,
            server_default='static',
        )
    )


def downgrade() -> None:
    op.drop_column('guide_sessions', 'conversation_history')
    op.drop_column('guide_sessions', 'mode')
