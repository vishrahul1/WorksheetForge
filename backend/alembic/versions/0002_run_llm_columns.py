"""add llm_provider and llm_model to runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("llm_provider", sa.String(50), nullable=True))
    op.add_column("runs", sa.Column("llm_model", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "llm_model")
    op.drop_column("runs", "llm_provider")
