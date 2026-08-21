"""supplier_prices: daily supplier price quotes per product

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_code", sa.String(10), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_supplier_prices_delivery_date", "supplier_prices", ["delivery_date"])
    op.create_index("idx_supplier_prices_product", "supplier_prices", ["product_id"])
    op.create_index("idx_supplier_prices_supplier", "supplier_prices", ["supplier_id"])
    op.create_unique_constraint(
        "uq_supplier_price_product_date",
        "supplier_prices",
        ["supplier_id", "product_id", "delivery_date"],
    )


def downgrade() -> None:
    op.drop_table("supplier_prices")
