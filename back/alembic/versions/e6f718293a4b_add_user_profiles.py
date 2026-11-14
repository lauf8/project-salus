"""Add independent astronaut and physician account profiles.

Revision ID: e6f718293a4b
Revises: d5f60718293a
"""
from alembic import op
import sqlalchemy as sa

revision = "e6f718293a4b"
down_revision = "d5f60718293a"
branch_labels = None
depends_on = None


def upgrade():
    # Existing accounts remain unclassified; mission permissions are unchanged.
    op.add_column("users", sa.Column("is_astronaut", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("is_physician", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("users", "is_astronaut", server_default=None)
    op.alter_column("users", "is_physician", server_default=None)


def downgrade():
    op.drop_column("users", "is_physician")
    op.drop_column("users", "is_astronaut")
