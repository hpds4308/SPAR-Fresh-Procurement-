"""supplier_prices: add admin adjusted_price alongside supplier's quoted price

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplier_prices", sa.Column("adjusted_price", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "supplier_prices",
        sa.Column("adjusted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "supplier_prices",
        sa.Column("adjusted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("supplier_prices", "adjusted_at")
    op.drop_column("supplier_prices", "adjusted_by")
    op.drop_column("supplier_prices", "adjusted_price")
