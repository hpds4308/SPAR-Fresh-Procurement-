"""purchase_orders: numbered PO Admin issues to a supplier from their
saved order for a delivery date (frozen snapshot of lines + prices)

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("po_number", sa.String(60), nullable=False, unique=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("issued_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("supplier_id", "delivery_date", name="uq_purchase_order_supplier_date"),
    )
    op.create_index("ix_purchase_orders_delivery_date", "purchase_orders", ["delivery_date"])


def downgrade() -> None:
    op.drop_index("ix_purchase_orders_delivery_date", table_name="purchase_orders")
    op.drop_table("purchase_orders")
