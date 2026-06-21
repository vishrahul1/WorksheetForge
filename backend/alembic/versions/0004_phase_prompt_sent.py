"""add prompt_sent to run_phases

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("run_phases", sa.Column("prompt_sent", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("run_phases", "prompt_sent")
