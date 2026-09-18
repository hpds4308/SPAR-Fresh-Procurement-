"""order_lines: add added_by_admin flag for lines Admin added directly to a branch's order

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_lines",
        sa.Column("added_by_admin", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("order_lines", "added_by_admin")
