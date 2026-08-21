"""delivery confirmation: received quantities + confirmation metadata

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-07

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("order_lines", sa.Column("received_quantity", sa.Numeric(10, 2), nullable=True))
    op.add_column("order_lines", sa.Column("receipt_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_lines", "receipt_notes")
    op.drop_column("order_lines", "received_quantity")
    op.drop_column("orders", "confirmed_by")
    op.drop_column("orders", "confirmed_at")
