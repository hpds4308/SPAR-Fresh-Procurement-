"""market_reference_prices: manually-entered competitor retail prices
(e.g. Keells) shown as a reference on the Supplier Prices page

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_reference_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="KEELLS"),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "source", "delivery_date", name="uq_reference_price_product_source_date"),
    )
    op.create_index(
        "idx_reference_prices_lookup", "market_reference_prices", ["source", "delivery_date"]
    )


def downgrade() -> None:
    op.drop_table("market_reference_prices")
