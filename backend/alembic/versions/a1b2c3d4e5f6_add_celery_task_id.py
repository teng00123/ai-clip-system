"""add celery_task_id to clip_jobs

Revision ID: a1b2c3d4e5f6
Revises: d6789d95d4a4
Create Date: 2026-04-14 17:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'd6789d95d4a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'clip_jobs',
        sa.Column('celery_task_id', sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('clip_jobs', 'celery_task_id')
