"""orders: branch order headers and lines

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="SUBMITTED"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_orders_branch", "orders", ["branch_id"])
    op.create_index("idx_orders_delivery_date", "orders", ["delivery_date"])
    op.create_index("idx_orders_status", "orders", ["status"])
    # One order per branch per delivery date — the app also checks this
    # before insert, but the constraint is the source of truth under
    # concurrent submissions.
    op.create_unique_constraint(
        "uq_orders_branch_delivery_date", "orders", ["branch_id", "delivery_date"]
    )

    op.create_table(
        "order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_code", sa.String(10), nullable=False),
        sa.Column("notes", sa.Text()),
    )
    op.create_index("idx_order_lines_order", "order_lines", ["order_id"])
    op.create_index("idx_order_lines_product", "order_lines", ["product_id"])


def downgrade() -> None:
    op.drop_table("order_lines")
    op.drop_table("orders")
