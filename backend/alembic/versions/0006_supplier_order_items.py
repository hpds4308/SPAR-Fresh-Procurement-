"""supplier_order_items: admin's direct branch-level order lines to a supplier

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_code", sa.String(10), nullable=False),
        sa.Column("agreed_price", sa.Numeric(10, 2)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_supplier_order_items_supplier_date", "supplier_order_items", ["supplier_id", "delivery_date"])
    op.create_index("idx_supplier_order_items_branch_date", "supplier_order_items", ["branch_id", "delivery_date"])
    op.create_index("idx_supplier_order_items_product", "supplier_order_items", ["product_id"])
    op.create_unique_constraint(
        "uq_supplier_order_item",
        "supplier_order_items",
        ["supplier_id", "branch_id", "product_id", "delivery_date"],
    )


def downgrade() -> None:
    op.drop_table("supplier_order_items")
