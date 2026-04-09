"""Initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-04-09

"""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('nickname', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )

    # ── projects ───────────────────────────────────────────────────────────────
    op.create_table(
        'projects',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── guide_sessions ─────────────────────────────────────────────────────────
    op.create_table(
        'guide_sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('answers', sa.Text(), nullable=True),
        sa.Column('brief', sa.Text(), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── scripts ────────────────────────────────────────────────────────────────
    op.create_table(
        'scripts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('paragraphs', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── videos ─────────────────────────────────────────────────────────────────
    op.create_table(
        'videos',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── clip_jobs ──────────────────────────────────────────────────────────────
    op.create_table(
        'clip_jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('video_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('progress', sa.Integer(), nullable=True),
        sa.Column('clip_plan', sa.Text(), nullable=True),
        sa.Column('output_path', sa.String(500), nullable=True),
        sa.Column('error_msg', sa.String(1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── indexes ────────────────────────────────────────────────────────────────
    op.create_index('ix_projects_user_id', 'projects', ['user_id'])
    op.create_index('ix_videos_project_id', 'videos', ['project_id'])
    op.create_index('ix_clip_jobs_project_id', 'clip_jobs', ['project_id'])
    op.create_index('ix_clip_jobs_status', 'clip_jobs', ['status'])


def downgrade() -> None:
    op.drop_table('clip_jobs')
    op.drop_table('videos')
    op.drop_table('scripts')
    op.drop_table('guide_sessions')
    op.drop_table('projects')
    op.drop_table('users')
